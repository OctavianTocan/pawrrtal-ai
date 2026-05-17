"""Types for the Pi-inspired agent loop.

Architecture mirrors @mariozechner/pi-agent-core from pi-mono:
  https://github.com/badlogic/pi-mono/blob/main/packages/agent/src/types.ts

Key separation:
  - AgentMessage: what the loop works with (can include UI-only messages)
  - LLMEvent: what providers emit while streaming
  - AgentEvent: what the loop emits to callers
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, TypedDict

# ---------------------------------------------------------------------------
# Content blocks (inside messages)
# ---------------------------------------------------------------------------


class TextContent(TypedDict):
    """Plain-text content block inside an assistant or user message."""

    type: Literal["text"]
    text: str


class ToolCallContent(TypedDict):
    """Tool-invocation content block emitted by the assistant."""

    type: Literal["toolCall"]
    tool_call_id: str
    name: str
    arguments: dict[str, Any]


class ToolResultContent(TypedDict):
    """Plain-text content block inside a ``toolResult`` message."""

    type: Literal["text"]
    text: str


# ---------------------------------------------------------------------------
# Agent-level messages (what the loop accumulates)
# ---------------------------------------------------------------------------


class UserMessage(TypedDict):
    """User-authored turn in the conversation history."""

    role: Literal["user"]
    content: str


class AssistantMessage(TypedDict):
    """One assistant turn (text + optional tool calls) with its stop reason.

    ``provider_state`` is an opaque, optional slot for provider-native
    replay metadata.  The loop never inspects its contents — providers
    own the keyspace.  Gemini stores its ``ModelContent`` here so
    follow-up turns can replay ``thought_signature`` bytes that Vertex
    rejects without; see
    https://ai.google.dev/gemini-api/docs/thought-signatures.

    Note: ``role``, ``content`` and ``stop_reason`` are mandatory; only
    ``provider_state`` is marked ``NotRequired`` so the discriminant
    fields keep TypeChecker-driven narrowing in ``_consume_llm_event``
    and ``_build_gemini_contents``.
    """

    role: Literal["assistant"]
    content: list[TextContent | ToolCallContent]
    stop_reason: str  # "stop" | "tool_use" | "error" | "aborted"
    provider_state: NotRequired[dict[str, Any]]


class ToolResultMessage(TypedDict):
    """Result message paired with a previous ``ToolCallContent``."""

    role: Literal["toolResult"]
    tool_call_id: str
    name: str
    content: list[ToolResultContent]
    is_error: bool


AgentMessage = UserMessage | AssistantMessage | ToolResultMessage


# ---------------------------------------------------------------------------
# LLM-level events (what StreamFn implementations yield)
# ---------------------------------------------------------------------------


class LLMTextDeltaEvent(TypedDict):
    """Incremental text chunk emitted by a provider during streaming."""

    type: Literal["text_delta"]
    text: str


class LLMThinkingDeltaEvent(TypedDict):
    """Incremental reasoning / chain-of-thought chunk.

    Yielded by providers whose model supports surfacing intermediate
    reasoning (Claude with extended-thinking blocks, Gemini with
    ``ThinkingConfig(include_thoughts=True)``, OpenAI o-series, etc.).
    The frontend renders these in a separate "thinking" pane so they
    don't appear in the final assistant transcript.
    """

    type: Literal["thinking_delta"]
    text: str


class LLMToolCallEvent(TypedDict):
    """Provider-side tool call (the loop dispatches to the matching AgentTool)."""

    type: Literal["tool_call"]
    tool_call_id: str
    name: str
    arguments: dict[str, Any]


class LLMDoneEvent(TypedDict):
    """Terminal event yielded by a provider to flush the assembled assistant turn.

    ``provider_state`` mirrors :class:`AssistantMessage.provider_state`:
    StreamFn implementations can return provider-native replay state
    here without exposing it to ``StreamEvent`` / Telegram / persistence.
    The loop copies it onto the resulting :class:`AssistantMessage` so
    the next turn's StreamFn can replay native content.

    The discriminant ``type`` and the loop-consumed ``stop_reason`` /
    ``content`` are mandatory; only ``provider_state`` is
    ``NotRequired`` so the union discriminant in ``LLMEvent`` keeps
    exhaustive narrowing.
    """

    type: Literal["done"]
    stop_reason: str
    content: list[TextContent | ToolCallContent]
    provider_state: NotRequired[dict[str, Any]]


LLMEvent = LLMTextDeltaEvent | LLMThinkingDeltaEvent | LLMToolCallEvent | LLMDoneEvent


# ---------------------------------------------------------------------------
# Agent-level events (what agent_loop() yields to callers)
# ---------------------------------------------------------------------------


class AgentStartEvent(TypedDict):
    """First event of any ``agent_loop`` invocation."""

    type: Literal["agent_start"]


class TurnStartEvent(TypedDict):
    """Boundary marker before each new assistant turn."""

    type: Literal["turn_start"]


class MessageStartEvent(TypedDict):
    """Boundary marker before each appended user / tool-result message."""

    type: Literal["message_start"]
    message: AgentMessage


class MessageEndEvent(TypedDict):
    """Boundary marker after each appended user / tool-result message."""

    type: Literal["message_end"]
    message: AgentMessage


class TextDeltaEvent(TypedDict):
    """Streaming assistant text chunk (provider-neutral counterpart of LLMTextDeltaEvent)."""

    type: Literal["text_delta"]
    text: str


class ThinkingDeltaEvent(TypedDict):
    """Streaming reasoning chunk (provider-neutral counterpart of LLMThinkingDeltaEvent).

    The loop forwards every ``LLMThinkingDeltaEvent`` from the provider
    as a ``ThinkingDeltaEvent`` so downstream wrappers (the chat router,
    SSE channel) can translate it into a ``StreamEvent`` of type
    ``"thinking"`` without growing a separate code path per provider.
    """

    type: Literal["thinking_delta"]
    text: str


class ToolCallStartEvent(TypedDict):
    """Loop announces the start of dispatching one tool call to its ``AgentTool``."""

    type: Literal["tool_call_start"]
    tool_call_id: str
    name: str


class ToolCallEndEvent(TypedDict):
    """Loop reports the arguments the tool call resolved to."""

    type: Literal["tool_call_end"]
    tool_call_id: str
    name: str
    arguments: dict[str, Any]


class ToolResultEvent(TypedDict):
    """Result of executing one tool call (or a permission denial / tool error)."""

    type: Literal["tool_result"]
    tool_call_id: str
    content: str
    is_error: bool


class TurnEndEvent(TypedDict):
    """Boundary marker after one assistant turn + tool results complete."""

    type: Literal["turn_end"]
    message: AssistantMessage
    tool_results: list[ToolResultMessage]


class AgentEndEvent(TypedDict):
    """Final event emitted when the loop exits normally."""

    type: Literal["agent_end"]
    messages: list[AgentMessage]


class AgentTerminatedEvent(TypedDict):
    """Emitted when the safety layer trips and the loop bails early.

    ``reason`` is a stable machine-readable string — callers (the chat
    router, tests, the frontend) match against it to render the
    appropriate user-facing notice.  ``details`` carries human-readable
    context (e.g. ``{"limit": 25, "observed": 25}``) for logs and the
    error message surfaced to the user.
    """

    type: Literal["agent_terminated"]
    reason: Literal[
        "max_iterations",
        "max_wall_clock",
        "consecutive_llm_errors",
        "consecutive_tool_errors",
    ]
    details: dict[str, Any]
    message: str


AgentEvent = (
    AgentStartEvent
    | TurnStartEvent
    | MessageStartEvent
    | MessageEndEvent
    | TextDeltaEvent
    | ThinkingDeltaEvent
    | ToolCallStartEvent
    | ToolCallEndEvent
    | ToolResultEvent
    | TurnEndEvent
    | AgentEndEvent
    | AgentTerminatedEvent
)


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


@dataclass
class AgentTool:
    """A callable tool the agent can invoke.

    ``execute`` receives the tool_call_id and keyword arguments matching
    the JSON schema parameters.  It must return a string result.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema object
    execute: Callable[..., Coroutine[Any, Any, str]]


# ---------------------------------------------------------------------------
# Agent context and loop config
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Shared state passed into and mutated by the agent loop."""

    system_prompt: str
    messages: list[AgentMessage]
    tools: list[AgentTool] = field(default_factory=list)


# StreamFn: what each provider implements.
# Takes messages (after transform + convert) and tools; yields LLMEvents.
StreamFn = Callable[
    [list[AgentMessage], list[AgentTool]],
    AsyncIterator[LLMEvent],
]

# TransformContextFn: prune/summarise messages before the LLM call.
TransformContextFn = Callable[
    [list[AgentMessage]],
    Coroutine[Any, Any, list[AgentMessage]],
]

# ShouldStopFn: return True to exit after the current turn.
ShouldStopFn = Callable[[AgentContext], bool]


@dataclass(frozen=True)
class AgentSafetyConfig:
    """Hard limits that prevent runaway agent loops.

    Every field accepts ``None`` to opt out of that specific guard.
    Defaults are conservative — they catch real runaways (model stuck in
    a tool loop, transient API errors retried forever, mis-configured
    workflow eating wall-clock) while leaving generous room for normal
    long agent turns (research, multi-step refactors).

    Tavi can disable any of these in `Settings` when running an agent
    that legitimately needs longer.  Set ``None`` to disable a specific
    guard; set the whole field to ``AgentSafetyConfig.disabled()`` to
    opt out entirely (escape hatch for trusted automations).

    Inspired by openclaw/openclaw#9912 (maxTurns/maxToolCalls),
    PR #38812 (tool-only safety valve), and issue #52147 (separating
    LLM-pending vs tool-executing timeout semantics).
    """

    #: Hard cap on assistant turns (LLM→tool→LLM round-trips) per
    #: ``agent_loop`` invocation.  ``None`` disables.  Default 25 covers
    #: deep research / refactor turns; runaway tool-call loops trip well
    #: before this.
    max_iterations: int | None = 25

    #: Wall-clock budget for the whole loop, in seconds.  Counted from
    #: the moment ``agent_loop`` is entered.  ``None`` disables.
    #: Default 300s (5 min) is generous for chat turns and matches the
    #: 600s cap minus headroom for streaming / network jitter.
    max_wall_clock_seconds: float | None = 300.0

    #: How many back-to-back stream errors (provider exception, network
    #: drop) we tolerate before bailing.  Resets on a successful stream.
    #: ``None`` disables retry-bail — a single error then immediately
    #: aborts.  Default 3.
    max_consecutive_llm_errors: int | None = 3

    #: How many back-to-back tool failures (``is_error=True`` results)
    #: we tolerate before bailing.  Resets on any successful tool call.
    #: Distinct from LLM errors so a flaky tool doesn't compound with a
    #: flaky model.  ``None`` disables.  Default 5.
    max_consecutive_tool_errors: int | None = 5

    #: Base backoff (seconds) between LLM retries; doubled each retry.
    #: First retry waits ``backoff``, second ``2*backoff``, etc.
    #: 0 disables backoff (retries fire immediately).
    llm_retry_backoff_seconds: float = 1.0

    @classmethod
    def disabled(cls) -> AgentSafetyConfig:
        """Return a config with every guard turned off.

        Use sparingly — only for trusted automation that genuinely needs
        unbounded loop time.  The chat path should always use the default
        config or a mildly relaxed variant.
        """
        return cls(
            max_iterations=None,
            max_wall_clock_seconds=None,
            max_consecutive_llm_errors=None,
            max_consecutive_tool_errors=None,
            llm_retry_backoff_seconds=0.0,
        )


# ---------------------------------------------------------------------------
# Permission gate (PR 03)
#
# The agent loop calls ``permission_check`` (when configured) before
# every tool ``execute``.  A ``deny`` short-circuits the call and emits
# a ``tool_result`` event with ``is_error=True``.  The optional
# ``permission_audit_sink`` lets the chat router persist a
# ``security_violation`` audit row without coupling the loop to the
# governance module.
#
# ``PermissionCheckFn`` itself lives in
# ``app.core.governance.permissions``.  We only declare the typing
# aliases here so ``AgentLoopConfig`` can reference them without a
# circular import.
# ---------------------------------------------------------------------------


class PermissionCheckResult(TypedDict):
    """Loop-side projection of :class:`governance.PermissionDecision`.

    The loop only needs three fields; importing the full dataclass
    would pull the governance package into ``agent_loop`` and
    re-introduce the circular dependency we deliberately avoid.
    """

    allow: bool
    reason: str | None
    violation_type: str | None


PermissionCheckFn = Callable[
    [str, dict[str, Any]],
    Coroutine[Any, Any, PermissionCheckResult],
]
"""Async predicate ``(tool_name, arguments) -> PermissionCheckResult``.

Bound by the chat router with the per-request ``PermissionContext``
already captured in the closure.  The loop is provider-neutral by
construction, so the signature is minimal.
"""


PermissionAuditSinkFn = Callable[
    [str, dict[str, Any], PermissionCheckResult],
    Coroutine[Any, Any, None],
]
"""Optional sink called after every denial so the chat router can
persist a ``security_violation`` audit row.  Errors raised by the
sink are swallowed by the loop — audit failures must never break a
turn."""


@dataclass
class AgentLoopConfig:
    """Configuration for a single agent_loop invocation.

    convert_to_llm: required — filters/converts AgentMessage[] to the
        subset the LLM provider understands (strips UI-only messages).
    transform_context: optional — async function that prunes or compresses
        the message list before every LLM call (e.g. sliding window).
    should_stop_after_turn: optional — sync predicate; return True to stop
        the loop after the current turn even if more tool calls are pending.
    safety: hard limits on iterations, wall-clock, retries, etc.  See
        :class:`AgentSafetyConfig`.  Defaults are conservative and
        appropriate for the chat path.
    permission_check: optional async permission gate called before every
        tool execution.  Returning ``allow=False`` skips the tool call
        and surfaces a ``tool_result`` event with ``is_error=True``.
        ``None`` (default) keeps the previous behaviour: every tool
        call dispatches to ``tool.execute`` directly.
    permission_audit_sink: optional async callback fired after every
        denial.  Receives ``(tool_name, arguments, decision)``.  Errors
        raised by the sink are swallowed; a failed audit must never
        break the turn.
    """

    convert_to_llm: Callable[[list[AgentMessage]], list[AgentMessage]]
    transform_context: TransformContextFn | None = None
    should_stop_after_turn: ShouldStopFn | None = None
    safety: AgentSafetyConfig = field(default_factory=AgentSafetyConfig)
    permission_check: PermissionCheckFn | None = None
    permission_audit_sink: PermissionAuditSinkFn | None = None
