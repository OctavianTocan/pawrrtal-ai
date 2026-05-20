"""xAI (Grok) provider — gRPC StreamFn adapter for the agent loop.

Wraps the official xai-sdk gRPC client (https://docs.x.ai,
https://github.com/xai-org/xai-sdk-python) so the agent loop can drive
Grok the same way it drives Gemini (``google-genai``) and Claude
(``claude-agent-sdk``).  Each provider is self-contained on its
vendor's first-party SDK — no shared HTTP-compat abstraction.

Design parity with :mod:`app.core.providers.gemini_provider`:

* ``make_xai_stream_fn`` builds a per-request :data:`StreamFn` closing
  over ``model_id``, optional ``workspace_id`` (for per-workspace
  ``XAI_API_KEY`` overrides), the assembled ``system_prompt``, a
  caller-supplied :class:`UsageAccumulator`, and the reasoning-effort
  knob.
* ``XaiLLM.stream`` runs :func:`agent_loop` against that StreamFn and
  translates each :class:`AgentEvent` into a :class:`StreamEvent` via
  :func:`_xai_events.agent_event_to_stream_event`.  After the loop
  returns, ``XaiLLM.stream`` emits one terminal
  ``StreamEvent(type="usage")`` carrying the per-turn totals the chat
  aggregator folds into the cost ledger.
* Tools, history, and the cross-provider permission gate flow through
  the same path as Gemini — the provider stays tool-agnostic per
  ``.claude/rules/architecture/no-tools-in-providers.md``.

xAI-specific surface this provider drives natively (via typed
proto / SDK fields, not ``extra_body``):

* ``reasoning_effort`` — Pawrrtal's four-level UI knob
  (``low | medium | high | extra-high``) is collapsed to xAI's
  two-level enum via :func:`_map_reasoning_effort`.  Grok 4.3 400s on
  anything else (https://docs.x.ai/docs/models/grok-4-3).
* ``search_parameters`` — xAI's Live Search was removed in May 2026;
  we no longer send this field.  Pawrrtal's canonical web tool is
  ``exa_search`` (gated by ``EXA_API_KEY``).  If xAI ships a
  replacement search surface, the knob will flow through here.
* ``response.cost_usd`` — the SDK does the
  ``cost_in_usd_ticks * 1e-10`` conversion for us via
  :mod:`xai_sdk.cost` (citing
  ``xai-proto/proto/xai/api/v1/usage.proto``).  We don't carry the
  constant locally.
* ``reasoning_content`` deltas — surfaced as
  :class:`LLMThinkingDeltaEvent` so the frontend's "thinking" pane
  (already wired for Gemini) lights up for Grok.

Multimodal image inputs are accepted on the protocol but not yet
bridged to xai-sdk's :func:`xai_sdk.chat.image`; the chat router can
still pass them conditionally without a runtime error.

Request- and response-shape helpers live in ``_xai_messages`` and
``_xai_stream`` so this module stays under the project's 500-line
budget (``scripts/check-file-lines.mjs``).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from xai_sdk import AsyncClient
from xai_sdk.proto import chat_pb2

from app.core.agent_loop import (
    AgentContext,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    AssistantMessage,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMThinkingDeltaEvent,
    StreamFn,
    UserMessage,
    agent_loop,
)
from app.core.agent_loop.safety_factory import safety_from_settings
from app.core.agent_loop.types import (
    PermissionCheckFn,
    TextContent,
)
from app.core.agent_system_prompt import (
    DEFAULT_AGENT_SYSTEM_PROMPT as _FALLBACK_SYSTEM_PROMPT,
)
from app.core.config import settings
from app.core.keys import resolve_api_key

from ._xai_events import agent_event_to_stream_event, identity_convert
from ._xai_messages import build_xai_messages, build_xai_tools
from ._xai_stream import (
    UsageAccumulator,
    deltas_from_chunk,
    done_event_from_response,
    tool_call_events_from_response,
    usage_record_from_response,
)
from .base import ReasoningEffort, StreamEvent

logger = logging.getLogger(__name__)


def _resolve_xai_api_key(workspace_root: Path | None) -> str:
    """Resolve the xAI API key for this request.

    Workspace overrides win over the gateway-global ``settings.xai_api_key``;
    :func:`resolve_api_key` already performs that fallback, so callers
    never need an ``or settings.xai_api_key`` suffix.
    """
    if workspace_root is not None:
        return resolve_api_key(workspace_root, "XAI_API_KEY") or ""
    return settings.xai_api_key


def _map_reasoning_effort(
    effort: ReasoningEffort | None,
) -> chat_pb2.ReasoningEffort | None:
    """Map Pawrrtal's five-level UI knob onto xAI's proto enum.

    Grok 4.3 accepts ``EFFORT_LOW`` or ``EFFORT_HIGH``
    (https://docs.x.ai/docs/models/grok-4-3) and 400s on anything
    else, including ``EFFORT_MEDIUM`` and ``EFFORT_NONE``.  The
    Pawrrtal UI surfaces ``minimal | low | medium | high | extra-high``
    — we collapse the lower three to ``EFFORT_LOW`` and the upper two
    to ``EFFORT_HIGH`` so the user gets a meaningful difference
    without overshooting xAI's schema.  ``None`` means "let xAI pick
    the model default" and the field is omitted from the request.
    """
    if effort is None:
        return None
    if effort in ("minimal", "low", "medium"):
        return chat_pb2.ReasoningEffort.EFFORT_LOW
    return chat_pb2.ReasoningEffort.EFFORT_HIGH


def make_xai_stream_fn(
    model_id: str,
    workspace_root: Path | None = None,
    *,
    system_prompt: str,
    reasoning_effort: ReasoningEffort | None = None,
    usage_sink: UsageAccumulator | None = None,
) -> StreamFn:
    """Build a :data:`StreamFn` backed by xai-sdk's gRPC ``AsyncClient``.

    Args:
        model_id: xAI model identifier (e.g. ``"grok-4.3"``).  Passed
            straight through to ``client.chat.create(model=...)``.
        workspace_root: Absolute path from the ``workspaces.path`` DB
            column, used to honour a per-workspace ``XAI_API_KEY``
            override.  ``None`` falls back
            to the gateway-global ``settings.xai_api_key``.
        system_prompt: System prompt for this StreamFn.  Captured into
            the returned closure and prepended as a ``ROLE_DEVELOPER``
            message on every call.  ``XaiLLM.stream`` builds a fresh
            StreamFn per request so the workspace-assembled prompt
            (SOUL.md + AGENTS.md + skills) is what the model sees.
        reasoning_effort: Optional reasoning-depth knob for grok-4.3.
            Mapped onto xAI's two-level proto enum via
            :func:`_map_reasoning_effort`.  ``None`` lets xAI pick the
            model default.
        usage_sink: Optional mutable :class:`UsageAccumulator` the
            StreamFn writes per-request usage into.  Shared across
            every agent_loop iteration for a single ``XaiLLM.stream``
            call so multi-turn tool-using conversations sum their cost
            correctly.  ``None`` skips usage capture entirely — useful
            for unit tests and utility callers that don't talk to the
            cost ledger.

    Returns:
        An async generator factory that yields ``LLMEvent`` instances.
        The factory is xai-specific; the surrounding :func:`agent_loop`
        stays provider-neutral.
    """

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        api_key = _resolve_xai_api_key(workspace_root)
        request_messages = build_xai_messages(messages, system_prompt)
        xai_tools = build_xai_tools(tools)
        effort = _map_reasoning_effort(reasoning_effort)

        try:
            # AsyncClient owns a gRPC channel; the context manager
            # closes it after the request so we don't leak file
            # descriptors on long-running uvicorn workers.
            async with AsyncClient(api_key=api_key) as client:
                async for event in _stream_one_request(
                    client=client,
                    model_id=model_id,
                    request_messages=request_messages,
                    xai_tools=xai_tools,
                    reasoning_effort=effort,
                    usage_sink=usage_sink,
                ):
                    yield event
        except Exception as exc:
            logger.error("xAI streaming error model=%s: %s", model_id, exc, exc_info=True)
            error_text = f"xAI error: {exc}"
            yield LLMTextDeltaEvent(type="text_delta", text=error_text)
            yield LLMDoneEvent(
                type="done",
                stop_reason="error",
                content=[TextContent(type="text", text=error_text)],
            )

    return stream_fn


async def _stream_one_request(
    *,
    client: AsyncClient,
    model_id: str,
    request_messages: list[chat_pb2.Message],
    xai_tools: object,
    reasoning_effort: chat_pb2.ReasoningEffort | None,
    usage_sink: UsageAccumulator | None,
) -> AsyncIterator[LLMEvent]:
    """Drive one ``chat.stream()`` round-trip through xai-sdk.

    Yields LLMEvents in the order the agent loop expects: text /
    thinking deltas during the stream, then any tool-call events
    sourced from the accumulated :class:`Response`, then the terminal
    :class:`LLMDoneEvent`.  Captures usage into ``usage_sink`` if
    supplied — the SDK populates ``Response.usage`` and
    ``Response.cost_usd`` once the stream completes.
    """
    chat = client.chat.create(
        model=model_id,
        messages=request_messages,
        tools=xai_tools,
        reasoning_effort=reasoning_effort,
    )

    final_response = None
    async for response, chunk in chat.stream():
        deltas = deltas_from_chunk(chunk)
        if deltas.thinking:
            # xAI streams reasoning per-token within one continuous
            # block, so every thinking delta from one ``chat.stream()``
            # call belongs to the same logical block — emit a constant
            # ``block_index=0`` so downstream renderers don't insert
            # spurious paragraph breaks between tokens (#353).
            yield LLMThinkingDeltaEvent(
                type="thinking_delta",
                text=deltas.thinking,
                block_index=0,
            )
        if deltas.text:
            yield LLMTextDeltaEvent(type="text_delta", text=deltas.text)
        final_response = response

    if final_response is None:
        # Empty stream — yield a clean done so the loop exits.
        yield LLMDoneEvent(type="done", stop_reason="stop", content=[])
        return

    for tool_event in tool_call_events_from_response(final_response):
        yield tool_event

    if usage_sink is not None:
        usage_sink.absorb(usage_record_from_response(final_response))

    yield done_event_from_response(final_response)


class XaiLLM:
    """AILLM backed by the agent_loop + an xai-sdk StreamFn.

    History is supplied by the caller (read from the Message table in
    ``api/chat.py``).  Tools are injected per-request via the
    :class:`AgentContext`, never composed inside the provider — see
    ``.claude/rules/architecture/no-tools-in-providers.md``.
    """

    def __init__(self, model_id: str, *, workspace_root: Path | None = None) -> None:
        """Construct an xAI provider bound to a specific model slug.

        Args:
            model_id: Bare xAI model identifier (e.g. ``"grok-4.3"``).
                The factory unwraps the canonical
                ``host:vendor/model`` form before constructing the
                provider.
            workspace_root: Absolute path from the ``workspaces.path`` DB
                column.  When supplied, a per-workspace ``XAI_API_KEY``
                override is honoured; otherwise the gateway-global key is
                used.  Optional to match :class:`ClaudeLLM` and
                :class:`GeminiLLM` for unauthenticated callers.
        """
        self._model_id = model_id
        self._workspace_root = workspace_root
        # ``_stream_fn`` is ``None`` in production; ``stream()`` builds
        # a fresh StreamFn per request so the per-request system prompt
        # is captured into the closure.  Tests monkeypatch this
        # attribute with a :class:`ScriptedStreamFn` — when set,
        # ``stream()`` honours the injection as-is.  See
        # ``.claude/rules/testing/agent-loop-testing-philosophy.md``.
        self._stream_fn: StreamFn | None = None

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,  # kept for AILLM protocol parity
        history: list[dict[str, str]] | None = None,
        tools: list[AgentTool] | None = None,
        system_prompt: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        permission_check: PermissionCheckFn | None = None,
        images: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run the agent loop and translate AgentEvents → StreamEvents.

        Args:
            question: The current user message.
            conversation_id: Used for logging only; xAI's API has no
                native session concept — the loop ships full history
                on every request.
            user_id: Authenticated user UUID (kept for protocol parity).
            history: Prior messages oldest-first as ``{role, content}``
                dicts.  Mapped onto :class:`UserMessage` /
                :class:`AssistantMessage` instances.
            tools: Optional list of cross-provider :class:`AgentTool`
                instances assembled by the chat router.
            system_prompt: System prompt for this turn.  ``None`` falls
                back to :data:`DEFAULT_AGENT_SYSTEM_PROMPT` so bare
                unit tests still work.
            reasoning_effort: Optional reasoning-depth knob.  Mapped
                onto grok-4.3's two-level enum via
                :func:`_map_reasoning_effort` and passed to xai-sdk.
                The model's chain-of-thought streams back as
                ``reasoning_content`` deltas and surfaces as
                :class:`StreamEvent` ``thinking`` events for the UI.
            permission_check: Optional cross-provider permission gate
                (PR 03b).  Threaded straight into
                :class:`AgentLoopConfig` so denial flows through the
                same code path Gemini and Claude use.
            images: Optional multimodal image inputs.  Accepted for
                protocol parity; not yet bridged to xai-sdk's
                :func:`xai_sdk.chat.image` content type (a non-empty
                list is logged and ignored so callers can switch on it
                without a runtime error).
        """
        if images:
            logger.debug(
                "XAI_IMAGES_IGNORED conversation_id=%s count=%d",
                conversation_id,
                len(images),
            )

        prior: list[AgentMessage] = []
        for m in history or []:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                prior.append(UserMessage(role="user", content=content))
            elif role == "assistant":
                prior.append(
                    AssistantMessage(
                        role="assistant",
                        content=[TextContent(type="text", text=content)],
                        stop_reason="stop",
                    )
                )

        context = AgentContext(
            system_prompt=system_prompt or _FALLBACK_SYSTEM_PROMPT,
            messages=prior,
            tools=list(tools or []),
        )
        prompt = UserMessage(role="user", content=question)
        config = AgentLoopConfig(
            convert_to_llm=identity_convert,
            safety=safety_from_settings(settings),
            permission_check=permission_check,
        )

        # One accumulator per ``stream()`` call, shared across every
        # StreamFn invocation the agent loop makes for this turn so a
        # multi-iteration tool-using conversation sums the cost correctly.
        usage_sink = UsageAccumulator()
        stream_fn = self._stream_fn or make_xai_stream_fn(
            self._model_id,
            self._workspace_root,
            system_prompt=context.system_prompt,
            reasoning_effort=reasoning_effort,
            usage_sink=usage_sink,
        )

        try:
            async for event in agent_loop([prompt], context, config, stream_fn):
                stream_event = agent_event_to_stream_event(event)
                if stream_event is not None:
                    yield stream_event

        except Exception as exc:
            yield StreamEvent(type="error", content=f"xAI provider error: {exc}")
            return

        # Terminal usage event — the chat aggregator folds it into the
        # cost ledger (see ``ChatTurnAggregator.apply`` and
        # ``app.channels._turn_cost.record_turn_cost_if_enabled``).
        # Skip when no chunk reported usage (test scripts, error-only
        # turns) so the ledger doesn't see spurious zero rows.
        if usage_sink.saw_any:
            yield StreamEvent(
                type="usage",
                input_tokens=usage_sink.input_tokens,
                output_tokens=usage_sink.output_tokens,
                cost_usd=usage_sink.cost_usd,
            )
