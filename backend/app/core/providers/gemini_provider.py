"""Google Gemini provider — StreamFn adapter for the agent loop."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from google import genai as genai  # noqa: PLC0414
from google.genai import types as gtypes

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
    LLMToolCallEvent,
    StreamFn,
    UserMessage,
    agent_loop,
)
from app.core.agent_loop.safety_factory import safety_from_settings
from app.core.agent_loop.types import (
    PermissionCheckFn,
    TextContent,
    ToolCallContent,
)
from app.core.agent_system_prompt import (
    DEFAULT_AGENT_SYSTEM_PROMPT as _FALLBACK_SYSTEM_PROMPT,
)
from app.core.config import settings
from app.core.governance.cost_tracker import compute_cost_usd

from ._gemini_events import agent_event_to_stream_event, identity_convert
from ._gemini_messages import (
    build_gemini_contents,
    build_gemini_tool_declarations,
    resolve_gemini_api_key,
    split_chunk_text,
    tool_calls_from_chunk,
)
from ._gemini_replay import function_call_content_for
from ._gemini_thinking import compose_thinking_config
from ._gemini_usage import (
    GeminiUsageAccumulator,
    absorb_request_usage,
    gemini_catalog_entry,
)
from .base import ReasoningEffort, StreamEvent

__all__ = [
    "GeminiLLM",
    "GeminiUsageAccumulator",
    "build_gemini_contents",
    "build_gemini_tool_declarations",
    "compose_thinking_config",
    "make_gemini_stream_fn",
    "resolve_gemini_api_key",
    "split_chunk_text",
    "tool_calls_from_chunk",
]

logger = logging.getLogger(__name__)

# ``_FALLBACK_SYSTEM_PROMPT`` is only used when no caller supplies a
# system prompt (unit tests, direct scripts).  Imported from
# ``app.core.agent_system_prompt`` so Gemini and Claude fall back to
# the same constant — otherwise the agent's identity would silently
# change when the user switched models.


# Message- and chunk-level helpers live in ``_gemini_messages`` so
# this module fits the 500-line file budget.


# ``compose_thinking_config`` / ``_GEMINI_THINKING_LEVEL`` live in
# ``_gemini_thinking`` so this module fits the 500-line file budget.


@dataclass
class _GeminiStreamState:
    """Mutable per-request scratch space for the Gemini StreamFn.

    Lives at module scope so the chunk-level helper can mutate it in
    place without inheriting the streaming for-loop's nesting depth.
    """

    full_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # Native ``ModelContent`` from whichever chunk produced the
    # function_call parts (Gemini delivers function calls in a single
    # chunk). Forwarded as ``LLMDoneEvent.provider_state["gemini"]
    # ["model_content"]`` so the next turn's request can replay
    # ``thought_signature`` bytes.
    function_call_content: gtypes.Content | None = None
    # Latest ``usage_metadata`` snapshot from this request. Gemini
    # emits cumulative counts on each chunk and a final snapshot on
    # the terminal chunk; we just keep overwriting and absorb the
    # last value into ``usage_sink`` at end-of-stream.
    last_usage_metadata: Any | None = None


def _events_from_chunk(chunk: Any, state: _GeminiStreamState) -> Iterator[LLMEvent]:
    """Yield events for one Gemini chunk and mutate ``state`` in place.

    Returns a generator so the caller can ``for event in _events_from_chunk(...)``
    one level shallower than inlining the body would force. Kept as a
    sync generator to stay flat — the outer ``async for chunk`` already
    awaits the SDK iterator.
    """
    # Track the latest ``usage_metadata`` — Gemini reports it
    # cumulatively per chunk, so the final non-None value is the
    # per-request total we want to bill.
    chunk_usage = getattr(chunk, "usage_metadata", None)
    if chunk_usage is not None:
        state.last_usage_metadata = chunk_usage
    # Split parts into thoughts (``part.thought is True``) and regular
    # text. ``chunk.text`` is a convenience accessor that concatenates
    # all text parts regardless of the thought flag, so we walk parts
    # explicitly to keep the two streams separate downstream.
    thinking_text, response_text = split_chunk_text(chunk)
    if thinking_text:
        yield LLMThinkingDeltaEvent(type="thinking_delta", text=thinking_text)
    if response_text:
        yield LLMTextDeltaEvent(type="text_delta", text=response_text)
        state.full_text += response_text

    chunk_tool_calls = tool_calls_from_chunk(chunk, len(state.tool_calls))
    if not chunk_tool_calls:
        return
    # Capture the original Gemini ``ModelContent`` so follow-up turns
    # can replay ``thought_signature`` bytes verbatim. Only the first
    # function-call chunk is preserved — Gemini emits function calls
    # in a single chunk so this is sufficient.
    if state.function_call_content is None:
        state.function_call_content = function_call_content_for(chunk)
    for tool_call in chunk_tool_calls:
        yield LLMToolCallEvent(
            type="tool_call",
            tool_call_id=tool_call["tool_call_id"],
            name=tool_call["name"],
            arguments=tool_call["arguments"],
        )
        state.tool_calls.append(tool_call)


def _build_done_event(state: _GeminiStreamState) -> LLMDoneEvent:
    """Build the terminal ``LLMDoneEvent`` from accumulated stream state.

    When the turn made any tool calls, forward the original Gemini
    ``ModelContent`` as opaque ``provider_state`` so the next iteration's
    request body replays the exact function_call parts (preserving
    ``thought_signature`` bytes that Gemini-3 / Vertex require).
    Pure-text turns omit the field — there is nothing for the next turn
    to replay.
    """
    stop_reason = "tool_use" if state.tool_calls else "stop"
    content: list[TextContent | ToolCallContent] = []
    if state.full_text:
        content.append(TextContent(type="text", text=state.full_text))
    content.extend(
        ToolCallContent(
            type="toolCall",
            tool_call_id=tc["tool_call_id"],
            name=tc["name"],
            arguments=tc["arguments"],
        )
        for tc in state.tool_calls
    )
    done_event: LLMDoneEvent = LLMDoneEvent(
        type="done",
        stop_reason=stop_reason,
        content=content,
    )
    if state.function_call_content is not None:
        done_event["provider_state"] = {"gemini": {"model_content": state.function_call_content}}
    return done_event


def make_gemini_stream_fn(
    model_id: str,
    workspace_root: Path | None = None,
    *,
    system_prompt: str,
    reasoning_effort: ReasoningEffort | None = None,
    usage_sink: GeminiUsageAccumulator | None = None,
) -> StreamFn:
    """Build a StreamFn backed by the google-genai SDK.

    Args:
        model_id: Gemini model identifier (e.g. ``"gemini-3.1-flash-lite-preview"``).
        workspace_root: Absolute path from the ``workspaces.path`` DB column,
            used to resolve a per-workspace ``GEMINI_API_KEY`` override. When
            ``None`` the gateway-global ``settings.google_api_key`` is used
            directly, matching ``ClaudeLLM``'s optional ``workspace_root``
            contract for unauthenticated background work (e.g. utility agents).
        system_prompt: The system prompt for this StreamFn.  Captured into the
            returned closure and bound to ``GenerateContentConfig.system_instruction``
            on every call.  ``GeminiLLM.stream`` builds a fresh StreamFn per
            request so the per-request prompt (assembled from the workspace's
            SOUL.md + AGENTS.md + CLAUDE.md + skills by the chat router) is
            what the model sees.  Required and keyword-only — there is no
            sensible "factory default" because every production caller already
            has the request prompt in scope and unit tests should be explicit
            about what they bind.
        reasoning_effort: Pawrrtal's per-turn reasoning knob, already
            resolved against the model's catalog support tuple by the
            chat-router backstop. ``None`` lets Gemini use its dynamic
            default; otherwise we forward the mapped Gemini level via
            ``thinking_level``.
        usage_sink: Optional mutable :class:`GeminiUsageAccumulator` the
            StreamFn writes per-request token counts into. Shared across
            every agent_loop iteration for a single ``GeminiLLM.stream``
            call so multi-turn tool-using conversations sum their
            spend correctly. ``None`` skips usage capture — useful for
            unit tests and utility callers that don't talk to the cost
            ledger. Thinking tokens are billed as output by Gemini (per
            https://ai.google.dev/gemini-api/docs/thinking), so we
            include them in ``output_tokens`` rather than dropping them.

    Returns:
        An async generator factory that yields ``LLMEvent``s. The generator
        is provider-specific; the calling ``agent_loop()`` is not.
    """

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        client = genai.Client(api_key=resolve_gemini_api_key(workspace_root))
        contents = build_gemini_contents(messages)
        # ``GenerateContentConfig.tools`` is typed as the wider union
        # ``list[Tool | Callable | mcp.Tool | ClientSession] | None``;
        # ``list`` is invariant, so we widen the local list at this seam
        # rather than make the helper return the wide type.
        gemini_tools: list[Any] | None = build_gemini_tool_declarations(tools)
        config = gtypes.GenerateContentConfig(
            system_instruction=system_prompt,
            # Pass None (not []) when there are no tools — some SDK versions raise on empty list.
            tools=gemini_tools or None,
            # TODO(pawrrtal-1qlk): Set automatic_function_calling disable=True
            # so google-genai only emits function_call parts and Pawrrtal's
            # provider-agnostic agent_loop remains the sole tool executor.
            # Docs: https://github.com/googleapis/python-genai/blob/main/README.md
            # Ask the model to emit reasoning chunks alongside the answer
            # when it supports it (gemini-2.5-pro / -flash, gemini-3-*
            # with thinking).  Older / non-thinking models silently
            # ignore both ``include_thoughts`` and ``thinking_level``,
            # so it's safe to set both unconditionally when the caller
            # supplied a knob.  ``thinking_level`` is the Gemini 3
            # parameter (``minimal | low | medium | high``); we map
            # Pawrrtal's five-level ``ReasoningEffort`` onto it via
            # :data:`_GEMINI_THINKING_LEVEL`.  Sending both
            # ``thinking_level`` and the legacy ``thinking_budget`` in
            # one request 400s — Pawrrtal never sets the latter so the
            # surface here stays clean.
            thinking_config=compose_thinking_config(
                reasoning_effort=reasoning_effort,
                model_id=model_id,
            ),
            automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True),
        )

        state = _GeminiStreamState()
        try:
            # google-genai's async ``generate_content_stream`` returns
            # an awaitable that resolves to an ``AsyncIterator`` (per the
            # SDK's own docstring example). The earlier code relied on
            # the implicit-coroutine-as-iter pattern; mypy 1.x rejects it.
            # The cast to ``ContentUnion`` widens our narrower
            # ``list[Content]`` to the SDK's published union — ``list`` is
            # invariant so the implicit conversion doesn't typecheck, but
            # every element is already a ``Content`` subclass.
            stream = await client.aio.models.generate_content_stream(
                model=model_id,
                contents=cast(gtypes.ContentListUnion, contents),
                config=config,
            )
            async for chunk in stream:
                for event in _events_from_chunk(chunk, state):
                    yield event
        except Exception as exc:
            # Log so the error is visible in app.log — previously swallowed silently.
            logger.error("Gemini streaming error model=%s: %s", model_id, exc, exc_info=True)
            error_text = f"Gemini error: {exc}"
            # Emit a text delta so the frontend shows the error instead of an empty bubble.
            yield LLMTextDeltaEvent(type="text_delta", text=error_text)
            yield LLMDoneEvent(
                type="done",
                stop_reason="error",
                content=[TextContent(type="text", text=error_text)],
            )
            return

        absorb_request_usage(usage_sink, state.last_usage_metadata)
        yield _build_done_event(state)

    return stream_fn


class GeminiLLM:
    """AILLM backed by the agent_loop + a Gemini StreamFn.

    History is supplied by the caller (read from our Message table in
    chat.py).  Tools are injected per-request via the AgentContext.
    """

    def __init__(self, model_id: str, *, workspace_root: Path | None = None) -> None:
        """Construct a Gemini provider.

        Args:
            model_id: Gemini model identifier.
            workspace_root: Absolute path from the ``workspaces.path`` DB
                column. When supplied, a per-workspace ``GEMINI_API_KEY``
                override is honoured; otherwise the gateway-global key is
                used. Optional to match ``ClaudeLLM``'s contract for
                unauthenticated callers.
        """
        self._model_id = model_id
        self._workspace_root = workspace_root
        # ``_stream_fn`` defaults to ``None`` because the production system
        # prompt isn't known until ``stream()`` is called — ``stream()``
        # builds a fresh StreamFn per request via ``make_gemini_stream_fn``
        # so the workspace-assembled prompt (SOUL.md + AGENTS.md +
        # CLAUDE.md + skills) is baked into the closure that turn.  Tests
        # monkeypatch this attribute to inject a deterministic
        # ``ScriptedStreamFn``; when set, ``stream()`` honours the
        # injection as-is.  See ``.claude/rules/testing/agent-loop-testing-philosophy.md``.
        self._stream_fn: StreamFn | None = None

    async def stream(
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
        """Run the agent loop and translate AgentEvents → StreamEvents for the frontend.

        Args:
            question: The current user message.
            conversation_id: Used for logging; not persisted inside this method.
            user_id: Authenticated user UUID (used for logging).
            history: Prior messages oldest-first as ``{role, content}`` dicts.
            tools: Optional list of AgentTools to make available this turn
                (e.g. workspace file tools built by ``make_workspace_tools``).
            system_prompt: System prompt for this turn.  Callers should
                always supply one (the chat router does, populated from
                workspace AGENTS.md per PR #113).  When ``None`` the
                provider falls back to ``_FALLBACK_SYSTEM_PROMPT`` so a
                bare unit test or direct script call still works.
            reasoning_effort: Accepted for protocol parity. Gemini Flash
                ignores this UI knob for now.
            permission_check: Optional cross-provider ``can_use_tool`` gate
                (PR 03b).  Threaded straight into ``AgentLoopConfig`` so the
                loop's tool dispatch consults it before every tool execution.
                ``None`` (the default) preserves the previous behaviour.
            images: Optional multimodal image inputs (PR 05 protocol
                parity).  Accepted for ``AILLM`` protocol parity with
                Claude; the Gemini-side wiring lands in PR 09 alongside
                the frontend composer.  For now a non-empty list is
                logged and ignored so callers can switch on it
                conditionally without a runtime error.
        """
        if images:
            logger.debug(
                "GEMINI_IMAGES_IGNORED conversation_id=%s count=%d",
                conversation_id,
                len(images),
            )
        # AgentMessage is a union alias (not callable); construct the correct TypedDict by role.
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

        # The chat router composes the full tool list (workspace tools,
        # web search, future capabilities) and hands it in via *tools*.
        # The provider stays tool-agnostic on purpose — see
        # `.claude/rules/architecture/no-tools-in-providers.md` and the
        # gate at `scripts/check-no-tools-in-providers.py`.
        context = AgentContext(
            system_prompt=system_prompt or _FALLBACK_SYSTEM_PROMPT,
            messages=prior,
            tools=list(tools or []),
        )
        prompt = UserMessage(role="user", content=question)
        # Safety config is read from app settings so limits are tuneable via
        # environment variables (AGENT_MAX_ITERATIONS, AGENT_MAX_WALL_CLOCK_SECONDS,
        # etc.) without a code deploy.  Defaults are conservative and appropriate
        # for the interactive chat path; raise them for long-running automations.
        config = AgentLoopConfig(
            convert_to_llm=identity_convert,
            safety=safety_from_settings(settings),
            permission_check=permission_check,
        )

        # In production ``_stream_fn`` is ``None`` and we build a fresh
        # StreamFn per request so the captured ``system_prompt`` matches
        # what the chat router assembled this turn.  Tests monkeypatch
        # ``_stream_fn`` with a ``ScriptedStreamFn``; when set we honour
        # the injection (the script doesn't care about the prompt or
        # usage accumulator).
        usage = GeminiUsageAccumulator()
        stream_fn = self._stream_fn or make_gemini_stream_fn(
            self._model_id,
            self._workspace_root,
            system_prompt=context.system_prompt,
            reasoning_effort=reasoning_effort,
            usage_sink=usage,
        )

        try:
            async for event in agent_loop([prompt], context, config, stream_fn):
                stream_event = agent_event_to_stream_event(event)
                if stream_event is not None:
                    yield stream_event

        except Exception as exc:
            yield StreamEvent(type="error", content=f"Gemini provider error: {exc}")
            return

        # Emit one terminal ``usage`` event so the chat aggregator can
        # fold per-turn token totals into the cost ledger. Gemini's
        # API doesn't ship a server-reported USD figure, so we
        # compute it locally from the catalog's per-mtok rates via
        # :func:`compute_cost_usd`. Thinking tokens are billed as
        # output (per the Gemini Thinking docs) and were folded into
        # ``output_tokens`` upstream in
        # :meth:`GeminiUsageAccumulator.absorb_request`. ``saw_any``
        # skips the emission on early failures so we don't poison
        # the ledger with a zero-token row.
        if usage.saw_any:
            cost_usd = compute_cost_usd(
                catalog_entry=gemini_catalog_entry(self._model_id),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
            yield StreamEvent(
                type="usage",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=cost_usd,
            )
