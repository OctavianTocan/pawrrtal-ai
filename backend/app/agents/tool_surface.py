"""Compose the per-turn tool list the agent has access to.

This module is the **single source of truth** for which tools the
agent is exposed to.  Adding a new tool means appending to
``build_agent_tools`` here — never reaching into a provider, and
never scattering tool selection across handlers.

Why a dedicated module instead of inlining in ``app.chat.router``:

  * The chat router's job is HTTP plumbing (auth, request body,
    streaming), not deciding which capabilities the agent has.
  * Future per-agent / per-user / per-conversation permission gating
    must live above the providers (see
    ``.claude/rules/architecture/no-tools-in-providers.md``).  Putting
    that logic in the chat handler would tangle it with the streaming
    code; putting it here keeps the gate testable in isolation.
  * It gives the test suite a single function to drive when verifying
    "does the agent see Exa when EXA_API_KEY is configured?"
    end-to-end — no mocking the FastAPI request cycle.

The function is sync on purpose: every tool factory it calls is sync,
and the composition itself does no I/O.  Async-ifying the signature
would force callers (the chat router today, anything else tomorrow)
to ``await`` for no benefit.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from app.agents.types import AgentTool
from app.infrastructure.config import settings
from app.infrastructure.keys import resolve_api_key
from app.plugins.adapters.tools import build_snapshot_agent_tools
from app.plugins.errors import PluginError
from app.plugins.host import get_plugin_host
from app.plugins.tool_context import ToolContext
from app.providers.catalog import first_authenticated_catalog_model
from app.tools.artifact_agent import make_artifact_tool
from app.tools.exa_search_agent import make_exa_search_tool
from app.tools.image_gen_agent import make_image_gen_tool
from app.tools.lcm_agents import (
    make_lcm_describe_tool,
    make_lcm_expand_query_tool,
    make_lcm_grep_tool,
    make_lcm_list_summaries_tool,
    make_lcm_search_tool,
)
from app.tools.markitdown_convert import make_markitdown_tool
from app.tools.now import (
    build_external_mcp_tools,
    make_now_tool,
    make_report_issue_tool,
)
from app.tools.plugin_catalog import make_search_plugin_capabilities_tool
from app.tools.send_message import SendFn, make_send_message_tool
from app.tools.workspace_files import make_workspace_tools

log = logging.getLogger(__name__)


def build_agent_tools(
    *,
    workspace_root: Path,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    send_fn: SendFn | None = None,
    surface: str | None = None,
    conversation_id: uuid.UUID | None = None,
    model_id: str | None = None,
    external_mcp_configs: list[dict[str, Any]] | None = None,
) -> list[AgentTool]:
    """Return the full ``AgentTool`` list for one chat turn.

    Args:
        workspace_root: The user's default workspace directory.  Passed
            to :func:`make_workspace_tools` so the resulting tools are
            **scoped** to that directory.  The path-resolution helper
            inside ``workspace_files.py`` rejects ``..`` traversal and
            absolute paths via ``ToolError(OUT_OF_ROOT)``, but — and
            this is the load-bearing word — *scoped*, not *proven
            unescapable*.  We have unit tests for the resolver, not
            adversarial evals against a real model trying to escape.
            Until those land (see bean ``pawrrtal-wsiq``), treat the
            boundary as a strong invariant we haven't yet proved
            under prompt pressure.
        user_id: Authenticated user UUID, used to resolve per-workspace
            API key overrides for tools that call external services.
        workspace_id: Active workspace UUID.  When supplied alongside
            ``user_id``, manifest-backed plugin tools are appended after
            the core tools.  When ``None`` — including in tests that
            don't need plugin tools — plugin tools are skipped; core
            tool composition is unaffected.
        send_fn: Optional channel delivery callback.  When supplied the
            ``send_message`` tool is added to the list so the agent can
            proactively push text and files back to the user.  Both the
            web path (via a per-request asyncio queue drained into the
            SSE stream) and the Telegram path supply one; the distinction
            is purely in how the callback delivers — not whether it exists.
        surface: Optional channel surface ("web", "telegram", "electron").
            When set to "telegram", PR 13's CCT-shaped capability tools
            (``send_image_to_user`` / ``send_voice_to_user`` /
            ``send_document_to_user``) are appended so a workspace
            authored against CCT's MCP names runs unchanged here.
        conversation_id: Active conversation UUID — required for the
            LCM history tools (``lcm_grep`` / ``lcm_describe`` /
            ``lcm_list_summaries`` / ``lcm_expand_query``) to scope
            their queries.  Omitted in non-chat call sites.
        model_id: Active model id — used by ``lcm_expand_query`` to
            pick which provider to send the focused recall prompt to.
            Falls back to a sane default when not supplied.
        external_mcp_configs: Optional list of user-configured external
            MCP server entries (``{"name", "config"}``). Each entry's
            tools are discovered and appended as cross-provider
            :class:`AgentTool` instances. ``None`` / empty skips the
            external MCP path entirely. Closes #317.

    Returns:
        A fresh list of :class:`AgentTool` ready to hand to a provider.
        Order is **stable**: workspace tools first (the agent's default
        operating surface), then capability-gated tools (web search,
        future capabilities), then any plugin-contributed tools.
        Stable order matters for the Claude bridge's ``allowed_tools``
        whitelist construction and for snapshot-style tests.
    """
    tools: list[AgentTool] = []

    # Filesystem access scoped to the workspace.  Always present —
    # the agent is fundamentally a notebook editor, and these are the
    # primitives it edits with.
    tools.extend(make_workspace_tools(workspace_root))

    # Web search via Exa.  Capability-gated on a key being configured —
    # either per-workspace or globally.  When `user_id` is supplied,
    # `resolve_api_key` already handles workspace-then-settings fallback,
    # so a single call is sufficient. The unauthenticated fallback (no
    # `user_id` — e.g. background jobs) reads `settings.exa_api_key`
    # directly.  The `workspace_id` guard is an auth-context check, not a
    # path check — it distinguishes authenticated chat turns (which have
    # a workspace-bound .env) from background callers (which don't).
    if workspace_id is not None:
        exa_key = resolve_api_key(workspace_root, "EXA_API_KEY")
    else:
        exa_key = settings.exa_api_key or None
    if exa_key:
        tools.append(make_exa_search_tool(workspace_root=workspace_root))

    # Artifact rendering.  Always present — the wire shape is purely
    # structural and the catalog of safe components is enforced on the
    # client, so there's no key/quota to gate on.  The chat router
    # picks up artifact tool-calls and lifts the spec into a sibling
    # SSE event (see ``app.chat.router`` and ``app.tools.artifact``).
    # ``surface`` flips the tool description between the read-only and
    # interactive catalogs — Telegram (text-only) sees the read-only one,
    # web/electron sees the interactive widget catalog. Validation is
    # surface-independent.
    tools.append(make_artifact_tool(surface=surface))

    # Image generation — pure tool: generates PNG, saves to workspace,
    # returns path.  The agent decides whether to send it via send_message.
    # Capability-gated on OPENAI_CODEX_OAUTH_TOKEN being resolvable.
    # Same auth-gate pattern as the Exa block above: `workspace_id`
    # distinguishes authenticated turns from background callers.
    if workspace_id is not None:
        codex_token = resolve_api_key(workspace_root, "OPENAI_CODEX_OAUTH_TOKEN")
    else:
        codex_token = None
    if codex_token:
        tools.append(make_image_gen_tool(workspace_root=workspace_root))

    # Document-to-Markdown conversion via markitdown.  Always present —
    # no external API key required; all conversion happens locally.
    tools.append(make_markitdown_tool(workspace_root=workspace_root))

    # Current wall-clock time.  Pure stdlib, no network — always present
    # so the model can re-query the clock mid-turn without burning
    # iterations on an Exa search.  Pairs with the time block in the
    # system prompt (see ``app.agents.runtime_context``) — the block lands
    # at turn start, the tool covers long-running multi-step turns.
    tools.append(make_now_tool())

    tools.append(make_search_plugin_capabilities_tool(workspace_root=workspace_root))

    # GitHub issue reporting.  Always present — the tool resolves
    # GITHUB_TOKEN at call time and returns a clear error when the
    # token is not configured, same pattern as cron tools with a
    # missing scheduler.
    tools.append(make_report_issue_tool(workspace_root=workspace_root))

    # Channel delivery — present for both web (asyncio-queue SSE drain)
    # and Telegram (MIME-aware bot API calls).  The mechanism differs;
    # the tool contract is identical.
    if send_fn is not None:
        tools.append(make_send_message_tool(workspace_root=workspace_root, send_fn=send_fn))
        # PR 13: when the surface is Telegram, also surface the
        # CCT-shaped capability tools (``send_image_to_user`` etc.)
        # so a workspace authored against CCT's MCP names runs
        # unchanged here.  These are thin wrappers over the same
        # ``SendFn``; the model gets a richer tool catalogue without
        # the rest of the chat router learning about Telegram.
        if surface == "telegram":
            from app.tools.telegram_tools import (  # noqa: PLC0415 — local import keeps the cross-channel tool surface lazy
                make_telegram_capability_tools,
            )

            tools.extend(make_telegram_capability_tools(send_fn))

    # LCM history tools — give the agent on-demand access to compacted
    # conversation history.  All four are gated on the LCM master switch
    # and a conversation_id being present.
    if settings.lcm_enabled and conversation_id is not None:
        tools.append(make_lcm_grep_tool(conversation_id=conversation_id))
        tools.append(make_lcm_search_tool(conversation_id=conversation_id))
        tools.append(make_lcm_list_summaries_tool(conversation_id=conversation_id))
        tools.append(make_lcm_describe_tool(conversation_id=conversation_id))
        if user_id is not None:
            expand_model_id = model_id or first_authenticated_catalog_model(workspace_root).id
            # The lcm_expand_query tool needs a concrete model to run its
            # sub-query. Channel callers normally pass a resolved model_id, but
            # webhook/Telegram paths can still build tools before that happens;
            # use the workspace-authenticated catalog head for those cases.
            tools.append(
                make_lcm_expand_query_tool(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    model_id=expand_model_id,
                )
            )

    # Plugin-contributed tools.  Additive only — core tools above are
    # unaffected.  Extracted into a helper so the main composition body
    # stays under the project's branch-count ceiling.
    tools.extend(
        _build_plugin_tools(
            workspace_root=workspace_root,
            user_id=user_id,
            workspace_id=workspace_id,
            send_fn=send_fn,
            conversation_id=conversation_id,
            model_id=model_id,
        )
    )

    # External MCP servers (#317) — additive at the tail so the core
    # tool surface is never destabilised by a slow or misbehaving
    # remote server. Discovery is best-effort per server: a failed
    # handshake is logged and the rest of the chat surface keeps
    # working with whatever did handshake successfully.
    tools.extend(build_external_mcp_tools(external_mcp_configs or []))

    return tools


def _build_plugin_tools(
    *,
    workspace_root: Path,
    user_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
    send_fn: SendFn | None,
    conversation_id: uuid.UUID | None,
    model_id: str | None,
) -> list[AgentTool]:
    """Build every active manifest-backed plugin tool.

    Skipped entirely when the workspace context isn't available
    (background jobs, tests without a workspace): plugins gate on workspace-scoped env keys,
    so they have nothing to resolve without a ``workspace_id + user_id``
    pair.
    """
    if workspace_id is None or user_id is None:
        return []
    return _build_manifest_plugin_tools(
        workspace_root=workspace_root,
        tool_context=ToolContext(
            workspace_id=workspace_id,
            workspace_root=workspace_root,
            user_id=user_id,
            conversation_id=conversation_id,
            model_id=model_id,
            send_fn=send_fn,
        ),
    )


def _build_manifest_plugin_tools(
    *,
    workspace_root: Path,
    tool_context: ToolContext,
) -> list[AgentTool]:
    """Build dynamic manifest-backed plugin tools for one workspace."""
    try:
        _previous, snapshot = get_plugin_host().reload(workspace_root=workspace_root)
    except PluginError as exc:
        log.warning("manifest plugin reload failed during tool composition: %s", exc)
        return []
    return build_snapshot_agent_tools(
        snapshot=snapshot,
        workspace_root=workspace_root,
        tool_context=tool_context,
    )
