"""Compose the per-turn tool list the agent has access to.

This module is the **single source of truth** for which tools the
agent is exposed to.  Adding a new tool means appending to
``build_agent_tools`` here — never reaching into a provider, and
never scattering tool selection across handlers.

Why a dedicated module instead of inlining in ``app.api.chat``:

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

import uuid
from pathlib import Path
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.config import settings
from app.core.keys import resolve_api_key
from app.core.plugins import (
    PreTurnHook,
    ToolContext,
    all_plugins,
    is_activated_by_env_keys,
)
from app.core.providers.catalog import default_model
from app.core.tools.artifact_agent import make_artifact_tool
from app.core.tools.exa_search_agent import make_exa_search_tool
from app.core.tools.image_gen_agent import make_image_gen_tool
from app.core.tools.lcm_agents import (
    make_lcm_describe_tool,
    make_lcm_expand_query_tool,
    make_lcm_grep_tool,
    make_lcm_list_summaries_tool,
    make_lcm_search_tool,
)
from app.core.tools.markitdown_convert import make_markitdown_tool
from app.core.tools.now import (
    build_external_mcp_tools,
    make_add_task_tool,
    make_complete_task_tool,
    make_cron_create_tool,
    make_cron_delete_tool,
    make_cron_list_tool,
    make_invoke_skill_tool,
    make_list_skills_tool,
    make_list_tasks_tool,
    make_now_tool,
    make_read_skill_tool,
)
from app.core.tools.python_exec import make_virtual_python_tool
from app.core.tools.send_message import SendFn, make_send_message_tool
from app.core.tools.workspace_files import make_workspace_tools


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
            ``user_id``, plugin tools (additive integrations registered
            under :mod:`app.core.plugins`) are appended after the core
            tools.  When ``None`` — including in legacy tests that
            haven't been updated yet — plugin tools are skipped; core
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
    # SSE event (see ``app.api.chat`` and ``app.core.tools.artifact``).
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
    # system prompt (see ``app.core.runtime_context``) — the block lands
    # at turn start, the tool covers long-running multi-step turns.
    tools.append(make_now_tool())

    # TASKS.md (#311 v1).  Three tiny tools that read/write the
    # per-workspace task list.  Imported off ``now`` to keep this
    # module under sentrux's ``no_god_files`` fan-out budget; the
    # implementations live in ``app.core.tools.tasks_md``.
    tools.append(make_add_task_tool(workspace_root=workspace_root))
    tools.append(make_list_tasks_tool(workspace_root=workspace_root))
    tools.append(make_complete_task_tool(workspace_root=workspace_root))

    # Skill discovery + invocation (#315).  Always present so the
    # Paw can reason about which skills the workspace exposes; the
    # tools themselves do no work when the workspace has no
    # ``skills/`` directory.  Re-exported off ``now`` to stay under
    # the sentrux fan-out budget.
    tools.append(make_list_skills_tool(workspace_root=workspace_root))
    tools.append(make_read_skill_tool(workspace_root=workspace_root))
    tools.append(make_invoke_skill_tool(workspace_root=workspace_root))

    # Cron scheduling (#313).  Three tools that wrap the live
    # JobScheduler — registered via ``set_active_scheduler`` in
    # ``backend/main.py``'s lifespan.  Gated on ``user_id`` so an
    # unauthenticated background path doesn't get the cron surface.
    # Tools handle the ``scheduler_enabled = False`` case themselves
    # via ``get_active_scheduler() is None``.
    if user_id is not None:
        tools.append(make_cron_create_tool(user_id=user_id))
        tools.append(make_cron_list_tool(user_id=user_id))
        tools.append(make_cron_delete_tool(user_id=user_id))

    # In-process Python execution.  Opt-in via
    # ``settings.virtual_python_enabled`` because the tool is *not*
    # sandboxed — the deployment model assumes a single trusted
    # operator (see ``app/core/tools/python_exec.py`` docstring).
    if settings.virtual_python_enabled:
        tools.append(
            make_virtual_python_tool(
                workspace_root=workspace_root,
                timeout_seconds=settings.virtual_python_timeout_seconds,
                output_cap_bytes=settings.virtual_python_output_cap_bytes,
            )
        )

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
            from app.core.tools.telegram_tools import (  # noqa: PLC0415 — local import keeps the cross-channel tool surface lazy
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
            # When the caller didn't pin a model, fall back to the
            # catalog's canonical default rather than a hardcoded
            # preview ID — hardcoded preview IDs drift the moment the
            # catalog moves (see commit 08318a1 for the analogous fix in
            # ``app.cli.commit``).
            expand_model_id = model_id or default_model().id
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
) -> list[AgentTool]:
    """Walk the plugin registry and return every activated plugin's tools.

    Skipped entirely when the workspace context isn't available (legacy
    callers, background jobs): plugins gate on workspace-scoped env keys,
    so they have nothing to resolve without a ``workspace_id + user_id``
    pair.
    """
    if workspace_id is None or user_id is None:
        return []
    ctx = ToolContext(
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        user_id=user_id,
        send_fn=send_fn,
    )
    out: list[AgentTool] = []
    for plugin in all_plugins():
        predicate = plugin.is_activated or is_activated_by_env_keys(plugin)
        if not predicate(ctx):
            continue
        out.extend(factory(ctx) for factory in plugin.tool_factories)
    return out


def build_pre_turn_hooks() -> list[PreTurnHook]:
    """Build the pre-turn hooks from the plugin registry."""
    out: list[PreTurnHook] = []
    for plugin in all_plugins():
        out.extend(plugin.pre_turn_hooks)
    return out
