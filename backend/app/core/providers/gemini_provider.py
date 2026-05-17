"""Google Gemini provider — StreamFn adapter for the agent loop."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from google import genai
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
    ToolResultMessage,
)
from app.core.agent_system_prompt import (
    DEFAULT_AGENT_SYSTEM_PROMPT as _FALLBACK_SYSTEM_PROMPT,
)
from app.core.config import settings
from app.core.keys import resolve_api_key

from ._gemini_events import agent_event_to_stream_event, identity_convert
from ._gemini_replay import function_call_content_for, replay_content_for
from .base import ReasoningEffort, StreamEvent

logger = logging.getLogger(__name__)

# `_FALLBACK_SYSTEM_PROMPT` is the system prompt this provider uses
# when *no caller supplies one*.  In production the chat router
# always supplies one (assembled from the workspace's SOUL.md +
# AGENTS.md per PR #113), so this fallback only fires for unit tests
# and direct-script callers that don't wire up the assembly
# pipeline.
#
# It's imported from `app.core.agent_system_prompt` instead of being
# a string literal here so that the Gemini and Claude providers fall
# back to the **same** constant.  Otherwise the agent's identity
# would silently change when the user switched models — which is the
# behaviour AGENTS.md was meant to make impossible.
#
# The local alias is kept for grep continuity with the previous
# in-file constant of the same name.


def _build_gemini_tool_declarations(
    tools: list[AgentTool],
) -> list[gtypes.Tool] | None:
    """Convert AgentTools to Gemini FunctionDeclarations."""
    if not tools:
        return None
    # This is how we declare the tools to the model.
    declarations = [
        gtypes.FunctionDeclaration(
            name=t.name,
            description=t.description,
            parameters_json_schema=t.parameters,
        )
        for t in tools
    ]
    return [gtypes.Tool(function_declarations=declarations)]


def _assistant_parts(content: list[TextContent | ToolCallContent]) -> list[gtypes.Part]:
    """Convert one assistant message's text/tool-call blocks to Gemini parts."""
    parts: list[gtypes.Part] = []

    for block in content:
        if block["type"] == "text":
            text = block["text"]
            if text.strip():
                parts.append(gtypes.Part.from_text(text=text))
            continue

        parts.append(
            gtypes.Part.from_function_call(
                name=block["name"],
                args=block["arguments"],
            )
        )

    return parts


def _tool_result_content(msg: ToolResultMessage) -> gtypes.Content:
    """Convert a loop tool result to Gemini's function-response content."""
    text: str = "\n".join(block["text"] for block in msg["content"])
    response_key: str = "error" if msg["is_error"] else "result"
    return gtypes.UserContent(
        parts=[
            gtypes.Part.from_function_response(
                name=msg["name"],
                response={response_key: text},
            )
        ]
    )


def _build_gemini_contents(messages: list[AgentMessage]) -> list[gtypes.Content]:
    """Convert AgentMessages to Gemini Contents, oldest-first.

    Args:
        messages: The list of AgentMessages to convert.

    Returns:
        The list of Gemini Contents.
    """
    contents: list[gtypes.Content] = []

    for msg in messages:
        if msg["role"] == "user":
            text = msg["content"]
            if text.strip():
                contents.append(gtypes.UserContent(parts=[gtypes.Part.from_text(text=text)]))
            continue
        if msg["role"] == "assistant":
            # When the assistant message carries the original Gemini
            # ``ModelContent`` (saved on the producing turn), replay it
            # verbatim.  This preserves ``thought_signature`` bytes that
            # Vertex / Gemini-3 require for follow-up tool turns:
            # https://ai.google.dev/gemini-api/docs/thought-signatures
            replay = replay_content_for(msg)
            if replay is not None:
                contents.append(replay)
                continue
            parts = _assistant_parts(msg["content"])
            if parts:
                contents.append(gtypes.ModelContent(parts=parts))
            continue
        contents.append(_tool_result_content(msg))

    return contents


def _resolve_gemini_api_key(user_id: uuid.UUID | None) -> str:
    """Resolve the Gemini API key for this request."""
    if user_id is not None:
        return resolve_api_key(user_id, "GEMINI_API_KEY") or ""
    return settings.google_api_key


def _split_chunk_text(chunk: Any) -> tuple[str, str]:
    """Return ``(thinking_text, response_text)`` for a streaming chunk.

    Gemini's thinking-capable models emit ``Part`` objects with a
    ``thought=True`` flag for chain-of-thought content; regular response
    text uses ``thought=False`` (or ``None``).  The ``chunk.text``
    convenience accessor concatenates *all* text parts regardless of the
    flag, so consumers that need to render the two streams separately
    must walk parts explicitly.

    Non-thinking models simply never set ``thought=True``, so the
    thinking string stays empty and the response string is identical to
    ``chunk.text``.
    """
    thinking_parts: list[str] = []
    response_parts: list[str] = []
    for candidate in chunk.candidates or []:
        if not candidate.content or not candidate.content.parts:
            continue
        for part in candidate.content.parts:
            text = getattr(part, "text", None)
            if not text:
                continue
            if getattr(part, "thought", False):
                thinking_parts.append(text)
            else:
                response_parts.append(text)
    return "".join(thinking_parts), "".join(response_parts)


def _tool_calls_from_chunk(chunk: Any, start_index: int) -> list[dict[str, Any]]:
    """Extract Gemini function-call parts from a streaming chunk.

    Only the name + args are surfaced to the agent loop; the enclosing
    ``ModelContent`` (with its ``thought_signature`` bytes) is captured
    separately by :func:`function_call_content_for` and forwarded as opaque
    ``provider_state`` on the terminal ``LLMDoneEvent``.
    """
    calls: list[dict[str, Any]] = []
    for candidate in chunk.candidates or []:
        if not candidate.content or not candidate.content.parts:
            continue
        for part in candidate.content.parts:
            if not part.function_call:
                continue
            fc = part.function_call
            fn_name = fc.name or ""
            tool_call_id = f"call-{fn_name}-{start_index + len(calls)}"
            calls.append(
                {
                    "tool_call_id": tool_call_id,
                    "name": fn_name,
                    "arguments": dict(fc.args) if fc.args else {},
                }
            )
    return calls


def make_gemini_stream_fn(
    model_id: str,
    user_id: uuid.UUID | None = None,
    system_prompt: str = _FALLBACK_SYSTEM_PROMPT,
) -> StreamFn:
    """Build a StreamFn backed by the google-genai SDK.

    Args:
        model_id: Gemini model identifier (e.g. ``"gemini-3.1-flash-lite-preview"``).
        user_id: Authenticated user UUID, used to resolve a per-workspace
            ``GEMINI_API_KEY`` override. When ``None`` the gateway-global
            ``settings.google_api_key`` is used directly, matching
            ``ClaudeLLM``'s optional ``user_id`` contract for unauthenticated
            background work (e.g. utility agents).
        system_prompt: The system prompt for this StreamFn.  Captured into the
            returned closure and bound to ``GenerateContentConfig.system_instruction``
            on every call.  ``GeminiLLM.stream`` builds a fresh StreamFn per
            request so the per-request prompt (assembled from the workspace's
            SOUL.md + AGENTS.md + CLAUDE.md + skills by the chat router) is
            what the model sees; defaulting to ``_FALLBACK_SYSTEM_PROMPT`` keeps
            direct-script callers (a few unit tests) working without ceremony.

    Returns:
        An async generator factory that yields ``LLMEvent``s. The generator
        is provider-specific; the calling ``agent_loop()`` is not.
    """

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        client = genai.Client(api_key=_resolve_gemini_api_key(user_id))
        contents = _build_gemini_contents(messages)
        # ``GenerateContentConfig.tools`` is typed as the wider union
        # ``list[Tool | Callable | mcp.Tool | ClientSession] | None``;
        # ``list`` is invariant, so we widen the local list at this seam
        # rather than make the helper return the wide type.
        gemini_tools: list[Any] | None = _build_gemini_tool_declarations(tools)
        config = gtypes.GenerateContentConfig(
            system_instruction=system_prompt,
            # Pass None (not []) when there are no tools — some SDK versions raise on empty list.
            tools=gemini_tools or None,
            # TODO(pawrrtal-1qlk): Set automatic_function_calling disable=True
            # so google-genai only emits function_call parts and Pawrrtal's
            # provider-agnostic agent_loop remains the sole tool executor.
            # Docs: https://github.com/googleapis/python-genai/blob/main/README.md
            # Ask the model to emit reasoning chunks alongside the answer
            # when it supports it (gemini-2.5-pro / -flash with thinking).
            # Older / non-thinking models silently ignore the flag, so this
            # is safe to send unconditionally.
            thinking_config=gtypes.ThinkingConfig(include_thoughts=True),
            automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True),
        )

        full_text = ""
        tool_calls: list[dict[str, Any]] = []
        # Holds the native ``ModelContent`` from whichever chunk produced
        # the function_call parts (Gemini delivers function calls in a
        # single chunk).  When set, the loop forwards it as
        # ``LLMDoneEvent.provider_state["gemini"]["model_content"]`` so
        # the next turn's request can replay ``thought_signature`` bytes.
        function_call_content: gtypes.Content | None = None

        try:
            # google-genai's async ``generate_content_stream`` returns
            # an awaitable that resolves to an ``AsyncIterator`` (per the
            # SDK's own docstring example). The earlier code relied on
            # the implicit-coroutine-as-iter pattern; mypy 1.x rejects it.
            stream = await client.aio.models.generate_content_stream(
                model=model_id,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                # Split parts into thoughts (``part.thought is True``) and
                # regular text.  ``chunk.text`` is a convenience accessor
                # that concatenates *all* text parts regardless of the
                # thought flag, so we walk parts explicitly to keep the
                # two streams separate downstream.
                thinking_text, response_text = _split_chunk_text(chunk)
                if thinking_text:
                    yield LLMThinkingDeltaEvent(type="thinking_delta", text=thinking_text)
                if response_text:
                    yield LLMTextDeltaEvent(type="text_delta", text=response_text)
                    full_text += response_text

                chunk_tool_calls = _tool_calls_from_chunk(chunk, len(tool_calls))
                if chunk_tool_calls:
                    # Capture the original Gemini ``ModelContent`` so
                    # follow-up turns can replay ``thought_signature``
                    # bytes verbatim.  Only the first function-call chunk
                    # is preserved — Gemini emits function calls in a
                    # single chunk so this is sufficient.
                    if function_call_content is None:
                        function_call_content = function_call_content_for(chunk)
                    for tool_call in chunk_tool_calls:
                        yield LLMToolCallEvent(
                            type="tool_call",
                            tool_call_id=tool_call["tool_call_id"],
                            name=tool_call["name"],
                            arguments=tool_call["arguments"],
                        )
                        tool_calls.append(tool_call)

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

        # Determine stop reason
        stop_reason = "tool_use" if tool_calls else "stop"

        content: list[TextContent | ToolCallContent] = []
        if full_text:
            content.append(TextContent(type="text", text=full_text))
        content.extend(
            ToolCallContent(
                type="toolCall",
                tool_call_id=tc["tool_call_id"],
                name=tc["name"],
                arguments=tc["arguments"],
            )
            for tc in tool_calls
        )

        # When the turn made any tool calls, forward the original Gemini
        # ``ModelContent`` as opaque ``provider_state`` so the next
        # iteration's request body replays the exact function_call parts
        # (preserving ``thought_signature`` bytes that Gemini-3 / Vertex
        # require).  Pure-text turns omit the field — there is nothing
        # for the next turn to replay.
        done_event: LLMDoneEvent = LLMDoneEvent(
            type="done",
            stop_reason=stop_reason,
            content=content,
        )
        if function_call_content is not None:
            done_event["provider_state"] = {"gemini": {"model_content": function_call_content}}
        yield done_event

    return stream_fn


class GeminiLLM:
    """AILLM backed by the agent_loop + a Gemini StreamFn.

    History is supplied by the caller (read from our Message table in
    chat.py).  Tools are injected per-request via the AgentContext.
    """

    def __init__(self, model_id: str, *, user_id: uuid.UUID | None = None) -> None:
        """Construct a Gemini provider.

        Args:
            model_id: Gemini model identifier.
            user_id: Authenticated user UUID, optional. When supplied, a
                per-workspace ``GEMINI_API_KEY`` override is honoured;
                otherwise the gateway-global key is used. Optional to match
                ``ClaudeLLM``'s contract for unauthenticated callers.
        """
        self._model_id = model_id
        self._user_id = user_id
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
        # the injection (the script doesn't care about the prompt).
        stream_fn = self._stream_fn or make_gemini_stream_fn(
            self._model_id,
            self._user_id,
            system_prompt=context.system_prompt,
        )

        try:
            async for event in agent_loop([prompt], context, config, stream_fn):
                stream_event = agent_event_to_stream_event(event)
                if stream_event is not None:
                    yield stream_event

        except Exception as exc:
            yield StreamEvent(type="error", content=f"Gemini provider error: {exc}")
