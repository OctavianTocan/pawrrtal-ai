"""xAI (Grok) provider — StreamFn adapter for the agent loop.

Wraps the OpenAI-compatible HTTP API exposed at ``https://api.x.ai/v1``
(docs: https://docs.x.ai/docs/api-reference) so the agent loop can drive
Grok the same way it drives Gemini and Claude.  The xAI surface is
intentionally OpenAI-compatible, so we use the upstream ``openai`` SDK
configured with ``base_url="https://api.x.ai/v1"`` rather than rolling
our own SSE parser — every streaming chunk, tool-call delta, and finish
reason then matches the well-understood OpenAI vocabulary.

Design parity with :mod:`app.core.providers.gemini_provider`:

* ``make_xai_stream_fn`` builds a per-request :data:`StreamFn` that
  closes over ``model_id``, optional ``workspace_id`` (for per-workspace
  ``XAI_API_KEY`` overrides), and the assembled ``system_prompt``.
* ``XaiLLM.stream`` runs :func:`agent_loop` against that StreamFn and
  translates each :class:`AgentEvent` into a :class:`StreamEvent` via
  :func:`_xai_events.agent_event_to_stream_event`.
* Tools, history, and the cross-provider permission gate flow through
  the same path as Gemini — the provider stays tool-agnostic per
  ``.claude/rules/architecture/no-tools-in-providers.md``.

Reasoning effort is accepted for protocol parity but ignored: Grok 4.3
does not surface a reasoning-effort knob via the OpenAI-compatible
endpoint at the time of writing (the dedicated reasoning variants are
separate model IDs).  Multimodal image inputs are accepted and logged
but not yet bridged — the chat router can still pass them
conditionally without a runtime error.

Request- and response-shape helpers live in ``_xai_messages`` and
``_xai_stream`` so this module stays under the project's 500-line
budget (``scripts/check-file-lines.mjs``).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import (
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionToolUnionParam,
)

from app.core.agent_loop import (
    AgentContext,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    AssistantMessage,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMToolCallEvent,
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
from ._xai_messages import build_xai_messages, build_xai_tool_declarations
from ._xai_stream import (
    ChunkAggregate,
    absorb_chunk,
    done_event_for,
    finalize_tool_calls,
)
from .base import ReasoningEffort, StreamEvent

logger = logging.getLogger(__name__)

# Public xAI endpoint — kept module-level so tests can monkeypatch it.
# The OpenAI SDK appends ``/chat/completions`` when ``base_url`` ends
# with ``/v1``, matching the path documented at
# https://docs.x.ai/docs/api-reference.
XAI_BASE_URL = "https://api.x.ai/v1"


def _resolve_xai_api_key(workspace_id: uuid.UUID | None) -> str:
    """Resolve the xAI API key for this request.

    Workspace overrides win over the gateway-global ``settings.xai_api_key``;
    :func:`resolve_api_key` already performs that fallback, so callers
    never need an ``or settings.xai_api_key`` suffix.
    """
    if workspace_id is not None:
        return resolve_api_key(workspace_id, "XAI_API_KEY") or ""
    return settings.xai_api_key


async def _open_xai_stream(
    *,
    client: AsyncOpenAI,
    model_id: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> AsyncStream[ChatCompletionChunk]:
    """Open the streaming chat-completions call against xAI.

    The openai SDK declares ``messages`` and ``tools`` as unions of
    TypedDicts; our wire dicts match the runtime contract but mypy
    can't narrow a dynamically-built ``dict[str, Any]`` into the
    union variant.  We narrow at this single SDK seam — never to
    ``Any`` (forbidden by the project mypy config).  Splitting the
    ``stream=True`` overload into two literal branches keeps mypy from
    widening the return to ``ChatCompletion | AsyncStream[...]``.
    """
    typed_messages = cast("list[ChatCompletionMessageParam]", messages)
    if tools is None:
        return await client.chat.completions.create(
            model=model_id,
            messages=typed_messages,
            stream=True,
        )
    typed_tools = cast("list[ChatCompletionToolUnionParam]", tools)
    return await client.chat.completions.create(
        model=model_id,
        messages=typed_messages,
        tools=typed_tools,
        stream=True,
    )


def make_xai_stream_fn(
    model_id: str,
    workspace_id: uuid.UUID | None = None,
    *,
    system_prompt: str,
) -> StreamFn:
    """Build a :data:`StreamFn` backed by xAI's OpenAI-compatible API.

    Args:
        model_id: xAI model identifier (e.g. ``"grok-4.3"``).  Passed
            straight through to the chat-completions endpoint.
        workspace_id: Active workspace UUID, used to honour a
            per-workspace ``XAI_API_KEY`` override.  ``None`` falls back
            to the gateway-global ``settings.xai_api_key``.
        system_prompt: System prompt for this StreamFn.  Captured into
            the returned closure and prepended as a ``role="system"``
            entry on every call.  ``XaiLLM.stream`` builds a fresh
            StreamFn per request so the workspace-assembled prompt
            (SOUL.md + AGENTS.md + skills) is what the model sees.

    Returns:
        An async generator factory that yields ``LLMEvent`` instances.
        The factory is provider-specific; the surrounding
        :func:`agent_loop` is not.
    """

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        api_key = _resolve_xai_api_key(workspace_id)
        client = AsyncOpenAI(api_key=api_key, base_url=XAI_BASE_URL)
        request_messages = build_xai_messages(messages, system_prompt)
        xai_tools = build_xai_tool_declarations(tools)
        aggregate = ChunkAggregate()

        try:
            stream = await _open_xai_stream(
                client=client,
                model_id=model_id,
                messages=request_messages,
                tools=xai_tools,
            )
            async for chunk in stream:
                text_delta = absorb_chunk(chunk, aggregate)
                if text_delta:
                    yield LLMTextDeltaEvent(type="text_delta", text=text_delta)
        except Exception as exc:
            logger.error("xAI streaming error model=%s: %s", model_id, exc, exc_info=True)
            error_text = f"xAI error: {exc}"
            yield LLMTextDeltaEvent(type="text_delta", text=error_text)
            yield LLMDoneEvent(
                type="done",
                stop_reason="error",
                content=[TextContent(type="text", text=error_text)],
            )
            return

        # Emit the assembled tool calls (if any) before the terminal
        # ``done`` event so the agent loop can dispatch them.  Ordering
        # by buffer index keeps the model's intended call sequence stable.
        completed_tool_calls = finalize_tool_calls(aggregate)
        for tc in completed_tool_calls:
            yield LLMToolCallEvent(
                type="tool_call",
                tool_call_id=tc["tool_call_id"],
                name=tc["name"],
                arguments=tc["arguments"],
            )
        yield done_event_for(aggregate, completed_tool_calls)

    return stream_fn


class XaiLLM:
    """AILLM backed by the agent_loop + an xAI StreamFn.

    History is supplied by the caller (read from the Message table in
    ``api/chat.py``).  Tools are injected per-request via the
    :class:`AgentContext`, never composed inside the provider — see
    ``.claude/rules/architecture/no-tools-in-providers.md``.
    """

    def __init__(self, model_id: str, *, workspace_id: uuid.UUID | None = None) -> None:
        """Construct an xAI provider bound to a specific model slug.

        Args:
            model_id: Bare xAI model identifier (e.g. ``"grok-4.3"``).
                The factory unwraps the canonical
                ``host:vendor/model`` form before constructing the
                provider.
            workspace_id: Active workspace UUID, optional.  When
                supplied, a per-workspace ``XAI_API_KEY`` override is
                honoured; otherwise the gateway-global key is used.
                Optional to match :class:`ClaudeLLM` and
                :class:`GeminiLLM` for unauthenticated callers.
        """
        self._model_id = model_id
        self._workspace_id = workspace_id
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
        user_id: uuid.UUID,
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
            conversation_id: Used for logging only; xAI's
                OpenAI-compatible API has no native session concept.
            user_id: Authenticated user UUID (used for logging).
            history: Prior messages oldest-first as ``{role, content}``
                dicts.  Mapped onto :class:`UserMessage` /
                :class:`AssistantMessage` instances.
            tools: Optional list of cross-provider :class:`AgentTool`
                instances assembled by the chat router.
            system_prompt: System prompt for this turn.  ``None`` falls
                back to :data:`DEFAULT_AGENT_SYSTEM_PROMPT` so bare
                unit tests still work.
            reasoning_effort: Accepted for protocol parity.  Grok 4.3
                does not surface a reasoning-effort knob via the
                OpenAI-compatible endpoint, so the value is ignored.
            permission_check: Optional cross-provider permission gate
                (PR 03b).  Threaded straight into
                :class:`AgentLoopConfig` so denial flows through the
                same code path Gemini and Claude use.
            images: Optional multimodal image inputs.  Accepted for
                protocol parity; not yet bridged to xAI's image-input
                shape (a non-empty list is logged and ignored so
                callers can switch on it without a runtime error).
        """
        if images:
            logger.debug(
                "XAI_IMAGES_IGNORED conversation_id=%s count=%d",
                conversation_id,
                len(images),
            )
        if reasoning_effort is not None:
            logger.debug(
                "XAI_REASONING_EFFORT_IGNORED conversation_id=%s value=%s",
                conversation_id,
                reasoning_effort,
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

        stream_fn = self._stream_fn or make_xai_stream_fn(
            self._model_id,
            self._workspace_id,
            system_prompt=context.system_prompt,
        )

        try:
            async for event in agent_loop([prompt], context, config, stream_fn):
                stream_event = agent_event_to_stream_event(event)
                if stream_event is not None:
                    yield stream_event

        except Exception as exc:
            yield StreamEvent(type="error", content=f"xAI provider error: {exc}")
