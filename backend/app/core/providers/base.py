"""Base protocol for AI providers."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypedDict

if TYPE_CHECKING:
    from app.core.agent_loop.types import AgentTool, PermissionCheckFn, ToolDisplayPayload

ReasoningEffort = Literal["minimal", "low", "medium", "high", "extra-high"]
"""Reasoning-depth values accepted from the chat UI.

Ordered lightest → heaviest. ``minimal`` is the fastest tier — Gemini
exposes it natively (Flash-Lite's default) and OpenAI accepts it on
every reasoning model; providers that lack it (Claude's adaptive
thinking, xAI's two-level enum) collapse it to ``low``. The
:mod:`app.core.providers.reasoning` resolver treats this tuple as the
canonical ladder for the nearest-supported fallback when the user
switches models mid-conversation.
"""


class StreamEvent(TypedDict, total=False):
    """A single event yielded from an AI provider's streaming response.

    All fields are optional because each event type only carries the keys
    relevant to it (e.g. ``delta`` carries ``content`` only, ``tool_use``
    carries ``name`` + ``input``).
    """

    type: str  # "delta" | "thinking" | "tool_use" | "tool_result" | "error" | "artifact" | "message" | "usage"
    content: str  # for delta and thinking
    name: str  # for tool_use
    input: dict[str, Any]  # for tool_use
    display: ToolDisplayPayload  # for tool_use
    tool_use_id: str  # for tool_result
    artifact: dict[str, Any]  # for artifact (id, title, spec)
    # ``message`` events emitted by the chat router's ``send_fn`` for
    # mid-turn pushes (text + optional file attachment back to the user).
    attachment: str  # for message — workspace-relative path
    mime: str | None  # for message — MIME type of the attachment, if any
    # Token + cost accounting (PR 04). Emitted by every provider on the
    # terminal message of a turn so the chat aggregator + cost ledger
    # have one canonical shape to consume regardless of model.
    input_tokens: int
    output_tokens: int
    cost_usd: float


class AILLM(Protocol):
    """Unified streaming interface for all AI providers.

    GeminiLLM uses ``history`` (read from our Message table) to build
    multi-turn context.  ClaudeLLM manages its own session continuity
    via ``resume`` and can ignore ``history``.
    """

    def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        history: list[dict[str, str]] | None = None,
        tools: list[AgentTool] | None = None,
        system_prompt: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        permission_check: PermissionCheckFn | None = None,
        images: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream response events for a user message.

        Implementations are async generators (``async def`` + ``yield``).
        The protocol declares the call signature with a plain ``def`` so
        mypy treats ``provider.stream(...)`` as returning the async
        iterator directly — declaring it ``async def`` would imply a
        coroutine that *returns* an iterator, requiring callers to
        ``await`` first, which is not what the runtime contract is.

        Args:
            question: Current user message.
            conversation_id: Conversation UUID (used for session continuity).
            user_id: Authenticated user UUID.
            history: Optional list of prior messages oldest-first, each a
                     dict with ``role`` (``"user"``/``"assistant"``) and
                     ``content`` keys.  Providers that manage their own
                     history (e.g. ClaudeLLM via ``resume``) may ignore
                     this.
            tools: Optional workspace-scoped AgentTools (read_file, write_file,
                     list_dir) to make available this turn.  Providers that
                     manage their own tool surface (e.g. ClaudeLLM) may ignore
                     this parameter.
            system_prompt: Optional override for the provider's default system
                     prompt.  When ``None`` the provider uses its own default.
            reasoning_effort: Optional reasoning-depth knob selected by the
                     user. Providers that do not support it may ignore it.
            permission_check: Optional async ``(tool_name, arguments)`` gate
                     (PR 03b).  When supplied, the provider plumbs it into
                     the cross-provider seam — ``AgentLoopConfig.permission_check``
                     for Gemini, ``ClaudeAgentOptions.can_use_tool`` (via the
                     tool bridge) for Claude — so the same policy is enforced
                     regardless of model.  ``None`` keeps the previous
                     behaviour: every tool call dispatches without a gate.
            images: Optional list of multimodal image inputs (PR 09).  Each
                     entry is ``{"data": <base64>, "media_type": "image/<mime>"}``.
                     Providers that support multimodal turn these into native
                     content blocks (Claude messages content blocks, Gemini
                     ``Part.from_bytes``).  Providers without multimodal
                     ignore the kwarg.
        """
        ...
