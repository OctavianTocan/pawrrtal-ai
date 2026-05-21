"""OpenCode Go provider — StreamFn adapter for the agent loop.

OpenCode Go is SST's hosted OpenAI-compatible gateway at
``https://opencode.ai/zen/go/v1`` that fronts open-weight coding models
(GLM-5.1, Kimi K2.6). Per the upstream catalogue at
https://github.com/sst/models.dev/blob/dev/providers/opencode-go/provider.toml
the protocol is plain OpenAI Chat Completions, so this provider is a
thin adapter that uses ``openai.AsyncOpenAI`` with ``base_url`` and
``api_key`` overrides and maps streamed deltas onto the loop's
provider-neutral ``LLMEvent`` shape.

Structure mirrors :mod:`gemini_provider`:

* ``make_opencode_go_stream_fn`` — closes over the system prompt and
  returns a ``StreamFn`` the loop drives one turn at a time.
* :class:`OpencodeGoLLM` — the ``AILLM`` instance the factory hands
  back to the chat router. Wraps ``agent_loop`` and translates
  ``AgentEvent`` outputs into the wire ``StreamEvent`` shape.

Cost: GLM-5.1 / Kimi K2.6 advertise interleaved chain-of-thought via a
sibling ``reasoning_content`` field on each streaming delta; the
gateway returns ``usage`` on the terminal chunk when the request is
sent with ``stream_options={"include_usage": True}``. The provider
multiplies the token counts by the catalogue's per-Mtok rates and
emits one ``StreamEvent(type="usage")`` after the loop completes so
the cost ledger aggregates correctly.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

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
from app.core.keys import resolve_api_key

from ._gemini_events import agent_event_to_stream_event, identity_convert
from ._opencode_go_events import (
    ToolCallBuffer,
    build_openai_messages,
    build_openai_tools,
    compute_cost_usd,
    read_reasoning,
)
from ._stream_logging import log_provider_stream_event
from .base import ReasoningEffort, StreamEvent

logger = logging.getLogger(__name__)


# Workspace-facing env-var name resolved per request via
# ``resolve_api_key`` — registered in :mod:`app.core.keys` so end users
# can override the gateway-global key in their encrypted workspace
# .env file.
_OPENCODE_API_KEY_NAME = "OPENCODE_API_KEY"


@dataclass(frozen=True)
class OpencodeGoLLMConfig:
    """Per-model wiring for the OpenCode Go provider.

    The factory builds one of these from the catalogue entry so the
    provider stays decoupled from :mod:`app.core.providers.catalog` and
    is trivially constructible from tests with explicit values.
    """

    cost_per_mtok_in_usd: float
    cost_per_mtok_out_usd: float
    base_url: str = "https://opencode.ai/zen/go/v1"


@dataclass
class _UsageAccumulator:
    """Mutable holder so the closure-captured StreamFn can report usage back.

    OpenAI streams ``usage`` only on the terminal chunk when the
    request opts in with ``stream_options={"include_usage": True}``. The
    StreamFn writes the counts here; :meth:`OpencodeGoLLM.stream` reads
    the totals once the agent loop finishes and emits a single
    ``StreamEvent(type="usage")`` so the cost ledger aggregates per
    request, not per loop iteration.
    """

    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, *, prompt_tokens: int | None, completion_tokens: int | None) -> None:
        """Fold one chunk's reported usage into the running totals.

        Args:
            prompt_tokens: Value off ``chunk.usage.prompt_tokens`` (or
                ``None`` when the SDK exposes no usage payload).
            completion_tokens: Value off ``chunk.usage.completion_tokens``
                (or ``None``).
        """
        if prompt_tokens:
            self.input_tokens += int(prompt_tokens)
        if completion_tokens:
            self.output_tokens += int(completion_tokens)


def _absorb_usage(chunk: Any, usage_acc: _UsageAccumulator) -> None:
    """Fold one chunk's optional ``usage`` payload into the accumulator.

    OpenAI sends the ``usage`` block only on the terminal chunk when
    the request opts in with ``stream_options={"include_usage": True}``;
    every other chunk has ``usage is None``. Pulled out so the streaming
    body can stay flat enough to satisfy the project nesting budget.
    """
    usage_blob = getattr(chunk, "usage", None)
    if usage_blob is None:
        return
    usage_acc.add(
        prompt_tokens=getattr(usage_blob, "prompt_tokens", None),
        completion_tokens=getattr(usage_blob, "completion_tokens", None),
    )


def _resolve_opencode_api_key(workspace_root: Path | None) -> str:
    """Resolve the OpenCode API key for this request.

    Mirrors the ``_resolve_gemini_api_key`` /
    ``_resolve_xai_api_key`` pattern — per-workspace override first,
    gateway-global ``settings.opencode_api_key`` second.  Falls
    through to the global when no workspace is in scope (background
    utility agents) or the workspace has not set an override.
    """
    if workspace_root is not None:
        return resolve_api_key(workspace_root, _OPENCODE_API_KEY_NAME) or ""
    return settings.opencode_api_key


def _drain_text_and_thinking(delta: Any) -> tuple[list[LLMEvent], str]:
    """Translate one streaming delta into ``(events_to_yield, response_text)``.

    Returning the response text alongside the event list lets the
    caller accumulate the full assistant string without opening an
    ``if`` inside its own ``for event in …: yield event`` loop — which
    would push the surrounding ``try / async for`` body past the
    project nesting budget (depth 3, enforced by
    ``scripts/check-nesting.py``).
    """
    out: list[LLMEvent] = []
    thinking_text = read_reasoning(delta)
    if thinking_text:
        out.append(LLMThinkingDeltaEvent(type="thinking_delta", text=thinking_text))
    response_text = getattr(delta, "content", None) or ""
    if response_text:
        out.append(LLMTextDeltaEvent(type="text_delta", text=response_text))
    return out, response_text


def _flush_tool_calls(
    buffer: ToolCallBuffer,
) -> tuple[list[LLMToolCallEvent], list[dict[str, Any]]]:
    """Materialise buffered tool-call deltas into LLM events + content blocks.

    Returns:
        ``(events, calls)`` where ``events`` is the list ready to yield
        from the StreamFn and ``calls`` carries the same data in the
        accumulator's dict form so the caller can use it to build the
        terminal ``LLMDoneEvent.content``.
    """
    calls = buffer.finalize()
    events = [
        LLMToolCallEvent(
            type="tool_call",
            tool_call_id=call["tool_call_id"],
            name=call["name"],
            arguments=call["arguments"],
        )
        for call in calls
    ]
    return events, calls


def _done_event(full_text: str, tool_calls: list[dict[str, Any]]) -> LLMDoneEvent:
    """Build the terminal ``LLMDoneEvent`` for one StreamFn invocation.

    Mirrors the assistant content shape Gemini emits so both providers
    feed the agent loop's accumulator the same dict union.
    """
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
    return LLMDoneEvent(type="done", stop_reason=stop_reason, content=content)


def make_opencode_go_stream_fn(
    model_id: str,
    workspace_root: Path | None,
    *,
    config: OpencodeGoLLMConfig,
    system_prompt: str,
    usage_acc: _UsageAccumulator,
) -> StreamFn:
    """Build a StreamFn backed by the OpenAI SDK pointed at OpenCode Go.

    Args:
        model_id: The bare model slug accepted by the gateway, e.g.
            ``"glm-5.1"`` or ``"kimi-k2.6"`` (no ``vendor/`` prefix —
            the canonical wire id is parsed upstream).
        workspace_root: Absolute path from the ``workspaces.path`` DB
            column; honoured for per-workspace
            API-key override.  ``None`` falls back to
            :attr:`Settings.opencode_api_key`.
        config: Per-model rates + gateway base URL.
        system_prompt: Captured into the closure and emitted as the
            first ``role="system"`` message on every call. Required and
            keyword-only — see ``make_gemini_stream_fn`` for the
            matching design note.
        usage_acc: Mutable usage holder; the closure writes totals into
            it so the surrounding :class:`OpencodeGoLLM` can emit a
            cumulative ``usage`` event after the loop ends.

    Returns:
        An async-generator factory the agent loop drives one turn at a
        time.
    """

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        api_key = _resolve_opencode_api_key(workspace_root)
        client = AsyncOpenAI(base_url=config.base_url, api_key=api_key or "missing")
        openai_messages = build_openai_messages(system_prompt=system_prompt, messages=messages)
        openai_tools = build_openai_tools(tools)

        tool_buffer = ToolCallBuffer()
        full_text = ""

        try:
            stream = await client.chat.completions.create(
                model=model_id,
                messages=openai_messages,  # type: ignore[arg-type]
                tools=openai_tools,  # type: ignore[arg-type]
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                _absorb_usage(chunk, usage_acc)
                choices = chunk.choices or []
                if not choices:
                    continue
                delta = choices[0].delta
                events, response_text = _drain_text_and_thinking(delta)
                full_text += response_text
                for event in events:
                    yield event
                tool_buffer.append(getattr(delta, "tool_calls", None))

        except Exception as exc:
            logger.error("OpenCode Go streaming error model=%s: %s", model_id, exc, exc_info=True)
            error_text = f"OpenCode Go error: {exc}"
            yield LLMTextDeltaEvent(type="text_delta", text=error_text)
            yield LLMDoneEvent(
                type="done",
                stop_reason="error",
                content=[TextContent(type="text", text=error_text)],
            )
            return

        tool_events, tool_calls = _flush_tool_calls(tool_buffer)
        for ev in tool_events:
            yield ev
        yield _done_event(full_text, tool_calls)

    return stream_fn


class OpencodeGoLLM:
    """``AILLM`` backed by the agent_loop + an OpenCode Go StreamFn.

    History is supplied by the caller (read from the Message table by
    the chat router, exactly like ``GeminiLLM``). Tools are injected
    per-request via ``AgentContext`` — the provider stays tool-agnostic
    per ``.claude/rules/architecture/no-tools-in-providers.md``.
    """

    def __init__(
        self,
        model_id: str,
        *,
        config: OpencodeGoLLMConfig,
        workspace_root: Path | None = None,
    ) -> None:
        """Construct an OpenCode Go provider.

        Args:
            model_id: Bare model slug the gateway accepts (no
                ``vendor/`` prefix — the canonical wire ID is parsed
                upstream by ``factory.resolve_llm``).
            config: Per-model rates + gateway base URL. The factory
                derives this from the matching
                ``catalog.ModelEntry``.
            workspace_root: Absolute path from the ``workspaces.path`` DB
                column.  When supplied, ``stream()`` resolves a
                per-workspace ``OPENCODE_API_KEY`` override; otherwise
                falls back to the gateway-global
                ``settings.opencode_api_key``.  Mirrors the
                ``GeminiLLM`` / ``XaiLLM`` contract.
        """
        self._model_id = model_id
        self._workspace_root = workspace_root
        self._config = config
        # ``_stream_fn`` defaults to ``None`` so production callers
        # build a fresh StreamFn per request (with the request's
        # system prompt). Tests monkeypatch this attribute to inject a
        # ``ScriptedStreamFn`` at the seam — see
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
            conversation_id: Used only for logging here.
            user_id: Authenticated user UUID, used for logging only.
                Per-workspace API-key resolution happens at
                construction time via ``self._workspace_root``.
            history: Prior messages oldest-first as ``{role, content}``
                dicts.
            tools: Optional ``AgentTool`` list assembled by the chat
                router.
            system_prompt: System prompt for this turn. Falls back to
                ``_FALLBACK_SYSTEM_PROMPT`` only when no caller supplied
                one (unit tests / direct scripts).
            reasoning_effort: Accepted for protocol parity. The
                gateway exposes interleaved reasoning unconditionally,
                so we don't translate this knob to a request parameter.
            permission_check: Optional cross-provider permission gate;
                threaded into ``AgentLoopConfig`` so the same denial
                surface fires regardless of model.
            images: Accepted for ``AILLM`` protocol parity. GLM-5.1
                advertises text-only inputs (``modalities.input =
                ["text"]``); Kimi K2.6 accepts images but the chat
                router's image plumbing lands separately. A non-empty
                list is logged and ignored for now.
        """
        if images:
            logger.debug(
                "OPENCODE_GO_IMAGES_IGNORED conversation_id=%s count=%d",
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

        usage_acc = _UsageAccumulator()
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

        stream_fn = self._stream_fn or make_opencode_go_stream_fn(
            self._model_id,
            self._workspace_root,
            config=self._config,
            system_prompt=context.system_prompt,
            usage_acc=usage_acc,
        )

        try:
            async for event in agent_loop([prompt], context, config, stream_fn):
                stream_event = agent_event_to_stream_event(event)
                if stream_event is not None:
                    log_provider_stream_event(
                        logger,
                        provider="OPENCODE_GO",
                        model=self._model_id,
                        conversation_id=conversation_id,
                        event=stream_event,
                    )
                    yield stream_event
        except Exception as exc:
            logger.error(
                "OpenCode Go provider error model=%s: %s",
                self._model_id,
                exc,
                exc_info=True,
            )
            stream_event = StreamEvent(
                type="error",
                content=f"OpenCode Go provider error: {exc}",
            )
            log_provider_stream_event(
                logger,
                provider="OPENCODE_GO",
                model=self._model_id,
                conversation_id=conversation_id,
                event=stream_event,
            )
            yield stream_event
            return

        if usage_acc.input_tokens or usage_acc.output_tokens:
            stream_event = StreamEvent(
                type="usage",
                input_tokens=usage_acc.input_tokens,
                output_tokens=usage_acc.output_tokens,
                cost_usd=compute_cost_usd(
                    input_tokens=usage_acc.input_tokens,
                    output_tokens=usage_acc.output_tokens,
                    cost_per_mtok_in_usd=self._config.cost_per_mtok_in_usd,
                    cost_per_mtok_out_usd=self._config.cost_per_mtok_out_usd,
                ),
            )
            log_provider_stream_event(
                logger,
                provider="OPENCODE_GO",
                model=self._model_id,
                conversation_id=conversation_id,
                event=stream_event,
            )
            yield stream_event
