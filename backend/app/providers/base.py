"""Base protocol for AI providers."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypedDict

if TYPE_CHECKING:
    from app.agents.types import AgentTool, ToolDisplayPayload

ReasoningEffort = Literal["minimal", "low", "medium", "high", "extra-high"]
"""Reasoning-depth values accepted from the chat UI.

Ordered lightest → heaviest. ``minimal`` is the fastest tier — Gemini
exposes it natively (Flash-Lite's default) and OpenAI accepts it on
every reasoning model; providers that lack it (Claude's adaptive
thinking, xAI's two-level enum) collapse it to ``low``. The
:mod:`app.providers.reasoning` resolver treats this tuple as the
canonical ladder for the nearest-supported fallback when the user
switches models mid-conversation.
"""


class StreamEvent(TypedDict, total=False):
    """A single event yielded from an AI provider's streaming response.

    All fields are optional because each event type only carries the keys
    relevant to it (e.g. ``delta`` carries ``content`` only, ``tool_use``
    carries ``name`` + ``input``).
    """

    type: str  # "delta" | "thinking" | "tool_use" | "tool_progress" | "tool_result" | "error" | "artifact" | "message" | "usage"
    content: str  # for delta and thinking
    # Block-boundary metadata for ``thinking`` events: same value = same
    # thinking block, different value = paragraph boundary between
    # blocks. Providers that stream per-token (xAI) emit a constant
    # value; providers that stream per-block (Gemini, Claude) increment
    # per block. Renderers MUST treat the field's absence as "same block
    # as the previous thinking event" for backward compatibility with
    # older stream functions. See #353.
    block_index: int
    name: str  # for tool_use
    input: dict[str, Any]  # for tool_use
    display: ToolDisplayPayload  # for tool_use
    tool_use_id: str  # for tool_use + tool_result — provider-native call id
    # ``True`` when a ``tool_result`` carries an error payload — set by the
    # Claude bridge (``_block_to_tool_result``) from
    # ``ToolResultBlock.is_error`` so downstream renderers can mark the turn
    # as failed without re-parsing the content. Other providers (Gemini, xAI,
    # opencode-go, gemini-cli) currently don't surface error / non-error on
    # tool results, so consumers should treat a missing key as ``False``.
    is_error: bool
    # Provider-supplied error category on ``type="error"`` events. Currently
    # opt-in (no provider emits it yet) — ``classify_error`` reads it as the
    # first hint before falling back to heuristic matching on the exception
    # type. Mirrors the public ``ErrorKind`` enum (see ``telegram_errors``).
    error_code: str
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
    # Provider diagnostics for cumulative thread/session counters. These
    # are intentionally not consumed by the cost ledger; ``input_tokens`` /
    # ``output_tokens`` stay per-turn.
    total_input_tokens: int
    total_output_tokens: int
    # ``thinking`` events: ``True`` when the delta is a "summary" thinking
    # block (renderers may collapse / style differently). Currently only
    # emitted by the openai_codex provider, which separates summary vs raw
    # reasoning text deltas. Other providers treat the absence as "raw".
    summary: bool
    # ``internal`` + ``artifact`` events: free-form subtype tag used by
    # the openai_codex provider to mark out-of-band signals
    # (``kind="codex_thread_created"``) and artifact subtypes
    # (``kind="image"``). Consumers route on ``type`` first and only
    # inspect ``kind`` when the type calls for it.
    kind: str
    # ``artifact`` events: opaque provider-supplied payload (the artifact
    # bytes / metadata). Renderers know how to interpret it based on
    # ``kind`` + ``provider``.
    data: Any
    # ``artifact`` / ``internal`` events: identifies the provider that
    # produced the artifact (``"openai_codex"``, etc.) so downstream
    # plugins can dispatch without inspecting the message envelope.
    provider: str
    # ``internal`` events: thread/session identifier the provider wants
    # the caller to persist for resume on the next turn (codex stores
    # this on the Conversation row).
    thread_id: str
    # ``transient`` events are user-visible progress chrome only. Channels
    # may render them, but aggregators and cost/trace accounting should not
    # persist them as assistant content.
    transient: bool
    # Optional coarse progress label for transient events.
    stage: str


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
            images: Optional list of multimodal image inputs (PR 09).  Each
                     entry is ``{"data": <base64>, "media_type": "image/<mime>"}``.
                     Providers that support multimodal turn these into native
                     content blocks (Claude messages content blocks, Gemini
                     ``Part.from_bytes``).  Providers without multimodal
                     ignore the kwarg.

        Provider-specific extensions live on the concrete provider's
        ``stream()`` signature, not on this Protocol. The openai_codex
        provider, for example, accepts ``codex_thread_id: str | None`` for
        SDK multi-turn continuity. Cross-provider callers pass these
        through ``**extra_kwargs`` and only forward them when actually set
        (see ``app.channels.turn_orchestrator._guarded_stream``) so unrelated
        providers don't see unknown keys.
        """
        ...
