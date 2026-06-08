"""Fast direct Antigravity API provider."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from app.agents import (
    DEFAULT_AGENT_SYSTEM_PROMPT as _FALLBACK_SYSTEM_PROMPT,
)
from app.agents import (
    AgentContext,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    AssistantMessage,
    StreamFn,
    UserMessage,
    run_model_tool_loop,
)
from app.agents.permissions import default_tool_permission_check
from app.agents.safety_factory import safety_from_settings
from app.agents.types import LLMEvent, TextContent
from app.infrastructure.config import settings
from app.providers._stream_logging import log_provider_stream_event
from app.providers.base import ReasoningEffort, StreamEvent
from app.providers.events import agent_event_to_stream_event, identity_convert

from .auth import AgyApiAuthError, ensure_agy_api_auth
from .client import stream_llm_events
from .events import AgyApiUsageAccumulator
from .messages import build_agy_generation_config

logger = logging.getLogger(__name__)

_WIRE_MODEL_ALIASES = {
    "gemini-3.1-pro-high": "gemini-pro-agent",
}


def resolve_agy_api_wire_model_id(model_id: str) -> str:
    """Return the Cloud Code Assist stream key for a catalog model id."""
    return _WIRE_MODEL_ALIASES.get(model_id, model_id)


async def make_agy_api_stream_fn(
    model_id: str,
    workspace_root: Path | None,
    *,
    system_prompt: str,
    reasoning_effort: ReasoningEffort | None,
    usage_sink: AgyApiUsageAccumulator,
) -> StreamFn:
    """Build a StreamFn backed by Antigravity's direct API."""
    auth = await ensure_agy_api_auth(workspace_root)
    wire_model_id = resolve_agy_api_wire_model_id(model_id)
    generation_config = build_agy_generation_config(
        model_id=model_id,
        reasoning_effort=reasoning_effort,
    )

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        async for event in stream_llm_events(
            auth=auth,
            model_id=wire_model_id,
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
            generation_config=generation_config,
            usage_sink=usage_sink,
        ):
            yield event

    return stream_fn


class AgyApiLLM:
    """``AILLM`` backed by Antigravity's Cloud Code Assist streaming API."""

    def __init__(self, model_id: str, *, workspace_root: Path | None = None) -> None:
        self._model_id = model_id
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
        """Stream one direct Antigravity API turn."""
        if images:
            logger.warning("AGY_API_IMAGES_UNSUPPORTED count=%d", len(images))
        prior = _history_to_agent_messages(history)
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
        usage = AgyApiUsageAccumulator()

        try:
            stream_fn = self._stream_fn or await make_agy_api_stream_fn(
                self._model_id,
                self._workspace_root,
                system_prompt=context.system_prompt,
                reasoning_effort=reasoning_effort,
                usage_sink=usage,
            )
        except AgyApiAuthError as exc:
            yield StreamEvent(type="error", content=f"Antigravity API auth unavailable: {exc}")
            return

        try:
            async for event in run_model_tool_loop([prompt], context, config, stream_fn):
                stream_event = agent_event_to_stream_event(event)
                if stream_event is None:
                    continue
                log_provider_stream_event(
                    logger,
                    provider="AGY_API",
                    model=self._model_id,
                    conversation_id=conversation_id,
                    event=stream_event,
                )
                yield stream_event
        except Exception as exc:
            logger.error(
                "Antigravity API provider error model=%s user_id=%s: %s",
                self._model_id,
                user_id,
                exc,
                exc_info=True,
            )
            yield StreamEvent(type="error", content=f"Antigravity API provider error: {exc}")
            return

        if usage.saw_any:
            stream_event = StreamEvent(
                type="usage",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=0.0,
            )
            log_provider_stream_event(
                logger,
                provider="AGY_API",
                model=self._model_id,
                conversation_id=conversation_id,
                event=stream_event,
            )
            yield stream_event


def _history_to_agent_messages(history: list[dict[str, str]] | None) -> list[AgentMessage]:
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
    return prior
