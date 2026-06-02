"""Cloud Code Assist stream parsing for Antigravity direct API."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, cast

from app.agents.types import (
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMThinkingDeltaEvent,
    LLMToolCallEvent,
    TextContent,
    ToolCallContent,
)
from app.providers.base import StreamEvent


@dataclass
class AgyApiUsageAccumulator:
    """Usage totals summed across every Antigravity request in one turn."""

    input_tokens: int = 0
    output_tokens: int = 0
    saw_any: bool = False

    def absorb_request(self, usage: dict[str, Any] | None) -> None:
        """Fold one request's terminal usage snapshot into the totals."""
        if usage is None:
            return
        prompt_tokens = _coerce_int(usage.get("promptTokenCount"))
        candidate_tokens = _coerce_int(usage.get("candidatesTokenCount"))
        thought_tokens = _coerce_int(usage.get("thoughtsTokenCount"))
        if prompt_tokens == 0 and candidate_tokens == 0 and thought_tokens == 0:
            return
        self.saw_any = True
        self.input_tokens += prompt_tokens
        self.output_tokens += candidate_tokens + thought_tokens


@dataclass
class AgyApiStreamState:
    """Mutable scratch state for one Cloud Code Assist stream."""

    full_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    function_call_parts: list[dict[str, Any]] = field(default_factory=list)
    last_usage_metadata: dict[str, Any] | None = None
    thinking_block_index: int = 0


def llm_events_from_response(
    response: object,
    state: AgyApiStreamState,
) -> Iterator[LLMEvent]:
    """Yield agent-loop LLM events for one Antigravity response chunk."""
    if not isinstance(response, dict):
        return
    usage = response.get("usageMetadata")
    if isinstance(usage, dict):
        state.last_usage_metadata = usage
    for part in _parts_from_response(response):
        yield from _events_from_part(part, state)


def build_done_event(state: AgyApiStreamState) -> LLMDoneEvent:
    """Build the terminal loop event from accumulated stream state."""
    content: list[TextContent | ToolCallContent] = []
    if state.full_text:
        content.append(TextContent(type="text", text=state.full_text))
    content.extend(
        ToolCallContent(
            type="toolCall",
            tool_call_id=tool_call["tool_call_id"],
            name=tool_call["name"],
            arguments=tool_call["arguments"],
        )
        for tool_call in state.tool_calls
    )
    done = LLMDoneEvent(
        type="done",
        stop_reason="tool_use" if state.tool_calls else "stop",
        content=content,
    )
    if state.function_call_parts:
        done["provider_state"] = {
            "agy_api": {
                "model_content": {
                    "role": "model",
                    "parts": state.function_call_parts,
                }
            }
        }
    return done


def stream_event_from_response(response: object) -> StreamEvent | None:
    """Return one raw StreamEvent for legacy direct parser tests."""
    state = AgyApiStreamState()
    for event in llm_events_from_response(response, state):
        stream_event = _llm_event_to_stream_event(event)
        if stream_event is not None:
            return stream_event
    usage = _usage_event_from_response(response)
    if usage is not None:
        return usage
    return None


def _events_from_part(part: dict[str, Any], state: AgyApiStreamState) -> Iterator[LLMEvent]:
    text = part.get("text")
    if isinstance(text, str) and text:
        if part.get("thought") is True:
            yield LLMThinkingDeltaEvent(
                type="thinking_delta",
                text=text,
                block_index=state.thinking_block_index,
            )
            state.thinking_block_index += 1
        else:
            yield LLMTextDeltaEvent(type="text_delta", text=text)
            state.full_text += text
    function_call = part.get("functionCall")
    if isinstance(function_call, dict):
        tool_call = _tool_call_from_function_call(function_call, len(state.tool_calls))
        state.tool_calls.append(tool_call)
        state.function_call_parts.append(_replay_part(part, function_call))
        yield LLMToolCallEvent(
            type="tool_call",
            tool_call_id=tool_call["tool_call_id"],
            name=tool_call["name"],
            arguments=tool_call["arguments"],
        )


def _tool_call_from_function_call(
    function_call: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    name = str(function_call.get("name") or "")
    raw_args = function_call.get("args")
    arguments = raw_args if isinstance(raw_args, dict) else {}
    tool_call_id = function_call.get("id")
    if not isinstance(tool_call_id, str) or not tool_call_id:
        tool_call_id = f"call-{name}-{index}-{uuid.uuid4().hex[:8]}"
    return {
        "tool_call_id": tool_call_id,
        "name": name,
        "arguments": arguments,
    }


def _replay_part(
    part: dict[str, Any],
    function_call: dict[str, Any],
) -> dict[str, Any]:
    replay: dict[str, Any] = {"functionCall": function_call}
    thought_signature = part.get("thoughtSignature")
    if isinstance(thought_signature, str) and thought_signature:
        replay["thoughtSignature"] = thought_signature
    return replay


def _parts_from_response(response: dict[str, Any]) -> Iterator[dict[str, Any]]:
    candidates = response.get("candidates")
    if not isinstance(candidates, list):
        return
    for candidate in candidates:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict):
                yield part


def _llm_event_to_stream_event(event: LLMEvent) -> StreamEvent | None:
    event_type = event["type"]
    if event_type == "text_delta":
        text_event = cast(LLMTextDeltaEvent, event)
        return StreamEvent(type="delta", content=text_event["text"])
    if event_type == "thinking_delta":
        thinking_event = cast(LLMThinkingDeltaEvent, event)
        stream_event = StreamEvent(type="thinking", content=thinking_event["text"])
        block_index = thinking_event.get("block_index")
        if isinstance(block_index, int):
            stream_event["block_index"] = block_index
        return stream_event
    if event_type == "tool_call":
        tool_event = cast(LLMToolCallEvent, event)
        return StreamEvent(
            type="tool_use",
            name=tool_event["name"],
            input=tool_event["arguments"],
            tool_use_id=tool_event["tool_call_id"],
        )
    return None


def _usage_event_from_response(response: object) -> StreamEvent | None:
    if not isinstance(response, dict):
        return None
    usage = response.get("usageMetadata")
    if not isinstance(usage, dict):
        return None
    input_tokens = _coerce_int(usage.get("promptTokenCount"))
    output_tokens = _coerce_int(usage.get("candidatesTokenCount"))
    thought_tokens = _coerce_int(usage.get("thoughtsTokenCount"))
    total_output_tokens = output_tokens + thought_tokens
    if input_tokens == 0 and total_output_tokens == 0:
        return None
    return StreamEvent(
        type="usage",
        input_tokens=input_tokens,
        output_tokens=total_output_tokens,
        cost_usd=0.0,
    )


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
