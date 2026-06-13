"""Claude Code PTY provider via the local OpenAI-compatible bridge."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from openai import AsyncOpenAI
from openai._types import NOT_GIVEN, Omit
from openai.types.chat import (
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageParam,
)

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
from app.agents.types import TextContent
from app.infrastructure.config import settings
from app.providers._stream_logging import log_provider_stream_event
from app.providers.base import ReasoningEffort, StreamEvent
from app.providers.events import agent_event_to_stream_event, identity_convert
from app.providers.opencode_go.events import (
    ToolCallBuffer,
    _done_event,
    _drain_text_and_thinking,
    _flush_tool_calls,
    build_openai_messages,
    build_openai_tools,
)

logger = logging.getLogger(__name__)

_SYNTHETIC_API_KEY = "claude-code-pty-openai-local"
_MODEL_MAP: dict[str, str] = {
    "claude-haiku-4-5": "haiku",
    "claude-sonnet-4-5": "sonnet",
    "claude-sonnet-4-6": "sonnet",
    "claude-opus-4-5": "opus",
    "claude-opus-4-6": "opus",
    "claude-opus-4-7": "opus",
}


@dataclass(frozen=True)
class ClaudeCodePtyLLMConfig:
    """Runtime settings for the Claude Code PTY OpenAI-compatible bridge."""

    base_url: str = "http://127.0.0.1:11435/v1"


def _bridge_model_id(model_id: str) -> str:
    """Return the model slug expected by ``ccpty serve``."""
    return _MODEL_MAP.get(model_id, model_id)


def make_claude_code_pty_stream_fn(
    model_id: str,
    *,
    config: ClaudeCodePtyLLMConfig,
    system_prompt: str,
    images: list[dict[str, str]] | None = None,
) -> StreamFn:
    """Build a StreamFn backed by ``ccpty serve``.

    The bridge is OpenAI-compatible and currently supports streaming chat
    completions. Tool calls are represented through the standard OpenAI
    ``tool_calls`` delta shape, then executed by Pawrrtal's provider-neutral
    loop exactly like OpenCode Go.
    """

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        client = AsyncOpenAI(base_url=config.base_url, api_key=_SYNTHETIC_API_KEY)
        openai_messages = build_openai_messages(
            system_prompt=system_prompt,
            messages=messages,
            images=images,
        )
        openai_tools = build_openai_tools(tools)
        typed_messages = cast("list[ChatCompletionMessageParam]", openai_messages)
        typed_tools: list[ChatCompletionFunctionToolParam] | Omit = (
            cast("list[ChatCompletionFunctionToolParam]", openai_tools)
            if openai_tools is not None
            else cast("Omit", NOT_GIVEN)
        )
        tool_buffer = ToolCallBuffer()
        full_text = ""

        try:
            stream = await client.chat.completions.create(
                model=_bridge_model_id(model_id),
                messages=typed_messages,
                tools=typed_tools,
                stream=True,
            )
            async for chunk in stream:
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
            logger.error(
                "Claude Code PTY streaming error model=%s: %s",
                model_id,
                exc,
                exc_info=True,
            )
            error_text = f"Claude Code PTY error: {exc}"
            yield LLMTextDeltaEvent(type="text_delta", text=error_text)
            yield LLMDoneEvent(
                type="done",
                stop_reason="error",
                content=[TextContent(type="text", text=error_text)],
            )
            return

        tool_events, tool_calls = _flush_tool_calls(tool_buffer)
        for event in tool_events:
            yield event
        yield _done_event(full_text, tool_calls)

    return stream_fn


class ClaudeCodePtyLLM:
    """``AILLM`` backed by the local Claude Code PTY bridge."""

    def __init__(
        self,
        model_id: str,
        *,
        config: ClaudeCodePtyLLMConfig,
        workspace_root: Path | None = None,
    ) -> None:
        """Construct a Claude Code PTY provider."""
        self._model_id = model_id
        self._config = config
        self._workspace_root = workspace_root
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
        """Run the provider-neutral loop against ``ccpty serve``."""
        del user_id, reasoning_effort
        prior: list[AgentMessage] = []
        for message in history or []:
            role = message.get("role")
            content = message.get("content", "")
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
        loop_config = AgentLoopConfig(
            convert_to_llm=identity_convert,
            permission_check=default_tool_permission_check,
            safety=safety_from_settings(settings),
        )
        stream_fn = self._stream_fn or make_claude_code_pty_stream_fn(
            self._model_id,
            config=self._config,
            system_prompt=context.system_prompt,
            images=images,
        )

        try:
            async for event in run_model_tool_loop([prompt], context, loop_config, stream_fn):
                stream_event = agent_event_to_stream_event(event)
                if stream_event is None:
                    continue
                log_provider_stream_event(
                    logger,
                    provider="CLAUDE_CODE_PTY",
                    model=self._model_id,
                    conversation_id=conversation_id,
                    event=stream_event,
                )
                yield stream_event
        except Exception as exc:
            logger.error(
                "Claude Code PTY provider error model=%s workspace=%s: %s",
                self._model_id,
                self._workspace_root,
                exc,
                exc_info=True,
            )
            yield StreamEvent(type="error", content=f"Claude Code PTY provider error: {exc}")
