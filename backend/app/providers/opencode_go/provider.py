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
  back to the chat router. Wraps ``run_model_tool_loop`` and translates
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

from openai import AsyncOpenAI

from app.agents import (
    DEFAULT_AGENT_SYSTEM_PROMPT as _FALLBACK_SYSTEM_PROMPT,
)
from app.agents import (
    AgentContext,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    AssistantMessage,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    StreamFn,
    UserMessage,
    run_model_tool_loop,
)
from app.agents.permissions import default_tool_permission_check
from app.agents.safety_factory import safety_from_settings
from app.agents.types import (
    TextContent,
)
from app.infrastructure.config import settings
from app.providers._stream_logging import log_provider_stream_event
from app.providers.base import ReasoningEffort, StreamEvent
from app.providers.events import agent_event_to_stream_event, identity_convert

from .events import (
    _OPENCODE_MISSING_KEY_NOTICE,
    ToolCallBuffer,
    _absorb_usage,
    _done_event,
    _drain_text_and_thinking,
    _flush_tool_calls,
    _resolve_opencode_api_key,
    _UsageAccumulator,
    build_openai_messages,
    build_openai_tools,
    compute_cost_usd,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpencodeGoLLMConfig:
    """Per-model wiring for the OpenCode Go provider.

    The factory builds one of these from the catalogue entry so the
    provider stays decoupled from :mod:`app.providers.catalog` and
    is trivially constructible from tests with explicit values.
    """

    cost_per_mtok_in_usd: float
    cost_per_mtok_out_usd: float
    base_url: str = "https://opencode.ai/zen/go/v1"


def make_opencode_go_stream_fn(
    model_id: str,
    workspace_root: Path | None,
    *,
    config: OpencodeGoLLMConfig,
    system_prompt: str,
    usage_acc: _UsageAccumulator,
    images: list[dict[str, str]] | None = None,
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
        images: Optional list of base64 multimodal image inputs.

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
        openai_messages = build_openai_messages(
            system_prompt=system_prompt,
            messages=messages,
            images=images,
        )
        openai_tools = build_openai_tools(tools)

        tool_buffer = ToolCallBuffer()
        full_text = ""

        try:
            # The openai SDK overloads expect a Literal model name from its
            # static catalog; we pass a runtime model_id string the gateway
            # owns, so the call-overload check rejects it here.
            stream = await client.chat.completions.create(  # type: ignore[call-overload]
                model=model_id,
                messages=openai_messages,
                tools=openai_tools,
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
    """``AILLM`` backed by the run_model_tool_loop + an OpenCode Go StreamFn.

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
            images: Accepted for ``AILLM`` protocol parity. GLM-5.1
                advertises text-only inputs (``modalities.input =
                ["text"]``); Kimi K2.6 accepts images but the chat
                router's image plumbing lands separately. A non-empty
                list is logged and ignored for now.
        """
        # Fail fast on missing API key with a user-readable notice. The
        # alternative — letting the request hit the gateway with
        # ``api_key="missing"`` — produces a 401 whose text is rendered
        # by the legacy Telegram path as a single-chunk delta and
        # frequently appears as no reply at all (#350). The check runs
        # before ``run_model_tool_loop`` so the loop's retry budget doesn't burn
        # three 401s before giving up.
        api_key = _resolve_opencode_api_key(self._workspace_root)
        if not api_key:
            logger.warning(
                "OPENCODE_GO_MISSING_API_KEY conversation_id=%s user_id=%s model=%s",
                conversation_id,
                user_id,
                self._model_id,
            )
            yield StreamEvent(type="error", content=_OPENCODE_MISSING_KEY_NOTICE)
            return

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
            permission_check=default_tool_permission_check,
            safety=safety_from_settings(settings),
        )

        stream_fn = self._stream_fn or make_opencode_go_stream_fn(
            self._model_id,
            self._workspace_root,
            config=self._config,
            system_prompt=context.system_prompt,
            usage_acc=usage_acc,
            images=images,
        )

        try:
            async for event in run_model_tool_loop([prompt], context, config, stream_fn):
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
