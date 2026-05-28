"""OpenAI-shape streaming helpers for the OpenCode Go provider.

Pure translation between the AgentLoop ``AgentMessage`` / ``AgentTool``
shape and the OpenAI Chat Completions wire format that the OpenCode Go
gateway (https://opencode.ai/zen/go/v1) speaks. No I/O, no SDK
construction — these helpers are isolated so ``opencode_go_provider``
stays under the 500-line file budget and is easy to unit-test.

The gateway is OpenAI-compatible at the protocol level but exposes
chain-of-thought via a sibling ``reasoning_content`` field on each
streamed delta (per the upstream catalogue's
``[interleaved] field = "reasoning_content"`` declaration). We map
that onto the loop's ``thinking_delta`` channel so it surfaces in the
chat router exactly like Gemini's thoughts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.agent_loop.types import (
    AgentMessage,
    AgentTool,
    AssistantMessage,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMThinkingDeltaEvent,
    LLMToolCallEvent,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
)
from app.core.config import settings
from app.core.keys import resolve_api_key

logger = logging.getLogger(__name__)


# OpenAI requires every tool message to carry a non-empty ``content``
# string; some upstream servers also reject ``role="tool"`` rows whose
# body is the empty string. Substitute a sentinel so the chat history
# stays well-formed even when a tool legitimately returned nothing.
_EMPTY_TOOL_RESULT_SENTINEL = "(no output)"


@dataclass
class ToolCallBuffer:
    """Accumulator for the partial ``tool_calls`` deltas OpenAI streams.

    Each streamed chunk's ``choices[0].delta.tool_calls`` is a list of
    fragments keyed by an integer ``index``. The provider may split a
    single call across many chunks: the first carries ``id`` and
    ``function.name``; subsequent chunks append to ``function.arguments``
    as raw JSON characters. This buffer concatenates the fragments and
    parses the final arguments string exactly once on
    :meth:`finalize`.
    """

    _calls: dict[int, dict[str, str]] = field(default_factory=dict)

    def append(self, delta_tool_calls: Any) -> None:
        """Merge one chunk's worth of tool-call deltas into the buffer.

        Args:
            delta_tool_calls: The ``delta.tool_calls`` list off an OpenAI
                streaming chunk. Each element is a pydantic model
                exposing ``index``, ``id``, and ``function.{name,
                arguments}``; missing fields read as ``None`` and are
                ignored.
        """
        if not delta_tool_calls:
            return
        for partial in delta_tool_calls:
            idx = getattr(partial, "index", None)
            if idx is None:
                continue
            slot = self._calls.setdefault(idx, {"id": "", "name": "", "arguments_json": ""})
            partial_id = getattr(partial, "id", None)
            if partial_id:
                slot["id"] = partial_id
            fn = getattr(partial, "function", None)
            if fn is None:
                continue
            fn_name = getattr(fn, "name", None)
            if fn_name:
                slot["name"] = fn_name
            fn_args = getattr(fn, "arguments", None)
            if fn_args:
                slot["arguments_json"] += fn_args

    def finalize(self) -> list[dict[str, Any]]:
        """Return one ``(tool_call_id, name, arguments)`` dict per buffered call.

        Calls are emitted in ascending ``index`` order so the model's
        intended sequence is preserved. Malformed argument JSON is
        downgraded to ``{"_raw": <string>}`` rather than raising — the
        tool dispatch path then surfaces a clear error to the model on
        the next turn instead of crashing the chat request.

        Returns:
            A list of ``{"tool_call_id", "name", "arguments"}`` dicts
            ready for :class:`LLMToolCallEvent` construction.
        """
        ordered = [self._calls[i] for i in sorted(self._calls)]
        result: list[dict[str, Any]] = []
        for slot in ordered:
            args_text = slot["arguments_json"] or "{}"
            try:
                arguments = json.loads(args_text)
            except json.JSONDecodeError:
                logger.warning(
                    "OPENCODE_GO_TOOL_ARGS_INVALID id=%s name=%s raw=%s",
                    slot["id"],
                    slot["name"],
                    args_text[:200],
                )
                arguments = {"_raw": args_text}
            result.append(
                {
                    "tool_call_id": slot["id"],
                    "name": slot["name"],
                    "arguments": arguments
                    if isinstance(arguments, dict)
                    else {"_value": arguments},
                }
            )
        return result


def read_reasoning(delta: Any) -> str:
    """Return chain-of-thought text off one OpenAI streaming delta.

    GLM-5.1 and Kimi K2.6 expose interleaved reasoning under
    ``delta.reasoning_content``. The OpenAI Python SDK accepts the
    field on newer versions; older versions strip it but preserve it
    in ``model_extra``. Check both so the provider works against any
    SDK pin without a hard version constraint.

    Args:
        delta: ``chunk.choices[0].delta`` from a streamed completion.

    Returns:
        The reasoning text fragment, or ``""`` when the delta carries
        none.
    """
    direct = getattr(delta, "reasoning_content", None)
    if direct:
        return str(direct)
    extra = getattr(delta, "model_extra", None)
    if isinstance(extra, dict):
        value = extra.get("reasoning_content")
        if value:
            return str(value)
    return ""


def build_openai_tools(tools: list[AgentTool]) -> list[dict[str, Any]] | None:
    """Convert ``AgentTool`` list into OpenAI ``tools`` parameter shape.

    Returns ``None`` (not ``[]``) when there are no tools so the
    request body omits the field entirely — some OpenAI-compatible
    backends reject an empty list.

    Args:
        tools: The provider-neutral tool list assembled by the chat
            router.

    Returns:
        OpenAI-shape ``[{"type": "function", "function": {...}}, ...]``
        or ``None`` when ``tools`` is empty.
    """
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def _assistant_text(content: list[TextContent | ToolCallContent]) -> str:
    """Concatenate every text block in an assistant message into one string.

    Tool-call blocks contribute to the OpenAI ``tool_calls`` field, not
    to the body; this helper only walks the text blocks so the caller
    can produce the ``"content"`` field independently.
    """
    return "".join(block["text"] for block in content if block["type"] == "text")


def _assistant_tool_calls(content: list[TextContent | ToolCallContent]) -> list[dict[str, Any]]:
    """Render an assistant message's tool-call blocks as OpenAI ``tool_calls``.

    Each block is replayed verbatim — ``tool_call_id`` matches the id
    the gateway assigned on the producing turn, so the follow-up
    ``role="tool"`` rows line up correctly.
    """
    calls: list[dict[str, Any]] = []
    for block in content:
        if block["type"] != "toolCall":
            continue
        calls.append(
            {
                "id": block["tool_call_id"],
                "type": "function",
                "function": {
                    "name": block["name"],
                    "arguments": json.dumps(block["arguments"]),
                },
            }
        )
    return calls


def _assistant_to_openai(msg: AssistantMessage) -> dict[str, Any]:
    """Build the OpenAI ``role="assistant"`` row for one assistant turn.

    The OpenAI API treats ``content`` and ``tool_calls`` as mutually
    optional — we include each only when populated to avoid sending
    ``null`` strings that some upstream servers reject.
    """
    text = _assistant_text(msg["content"])
    tool_calls = _assistant_tool_calls(msg["content"])
    row: dict[str, Any] = {"role": "assistant"}
    if text:
        row["content"] = text
    if tool_calls:
        row["tool_calls"] = tool_calls
    # OpenAI's schema requires either content or tool_calls to be
    # present — if a turn was pure refusal/aborted we still need a
    # body, so fall back to an empty string in that edge case.
    if "content" not in row and "tool_calls" not in row:
        row["content"] = ""
    return row


def _tool_result_to_openai(msg: ToolResultMessage) -> dict[str, Any]:
    """Build the OpenAI ``role="tool"`` row for one tool-result message."""
    text = "\n".join(block["text"] for block in msg["content"])
    return {
        "role": "tool",
        "tool_call_id": msg["tool_call_id"],
        "name": msg["name"],
        "content": text or _EMPTY_TOOL_RESULT_SENTINEL,
    }


def build_openai_messages(
    *,
    system_prompt: str,
    messages: list[AgentMessage],
    images: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Convert ``AgentMessage`` history into OpenAI chat messages.

    The system prompt is always emitted first so the caller doesn't have
    to remember to prepend it. UI-only message types are filtered out
    upstream by ``identity_convert``; this helper only handles the three
    LLM-visible roles.

    Args:
        system_prompt: The system prompt captured by the StreamFn
            closure at request build time.
        messages: The LLM-visible slice produced by
            ``AgentLoopConfig.convert_to_llm``.
        images: Optional list of base64 multimodal image inputs.
            Appended to the last user message in the list.

    Returns:
        A list of dicts ready to pass straight to
        ``client.chat.completions.create(messages=...)``.
    """
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    # Find the last user message's index so we attach the current turn's images to it
    last_user_idx = -1
    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            last_user_idx = idx

    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            user_content = msg["content"]
            if idx == last_user_idx and images:
                content_list: list[dict[str, Any]] = [{"type": "text", "text": user_content}]
                for img in images:
                    if "data" in img:
                        media_type = img.get("media_type", "image/png")
                        data_uri = f"data:{media_type};base64,{img['data']}"
                        content_list.append({"type": "image_url", "image_url": {"url": data_uri}})
                out.append({"role": "user", "content": content_list})
            else:
                out.append({"role": "user", "content": user_content})
            continue
        if msg["role"] == "assistant":
            out.append(_assistant_to_openai(msg))
            continue
        out.append(_tool_result_to_openai(msg))
    return out


_OPENCODE_API_KEY_NAME = "OPENCODE_API_KEY"

# User-facing notice surfaced when neither the workspace nor the gateway
# has an OpenCode API key configured.
_OPENCODE_MISSING_KEY_NOTICE = (
    "OpenCode API key not configured. Set OPENCODE_API_KEY in your "
    "workspace .env file or configure OPENCODE_API_KEY on the gateway "
    "to use Kimi K2.6 / GLM-5.1 via OpenCode Go."
)


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
        # OpenCode Go streams reasoning per-token via ``reasoning_content``
        # — one continuous logical block per stream attempt. Emit a
        # constant ``block_index=0`` so the channel renderer doesn't
        # insert paragraph breaks between consecutive tokens (#353).
        out.append(
            LLMThinkingDeltaEvent(
                type="thinking_delta",
                text=thinking_text,
                block_index=0,
            )
        )
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


# Token-count denominator for the catalogue's per-million-token rates.
_TOKENS_PER_MTOK = 1_000_000


def compute_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    cost_per_mtok_in_usd: float,
    cost_per_mtok_out_usd: float,
) -> float:
    """Return the dollar cost of one turn from token counts and catalogue rates.

    OpenCode Go reports ``usage.prompt_tokens`` / ``completion_tokens``
    on the final streamed chunk when the request includes
    ``stream_options={"include_usage": True}``. The gateway does not
    return a precomputed dollar total, so the provider does the
    multiplication using the rates stored on the ``ModelEntry`` (which
    mirror upstream's ``[cost]`` table).

    Args:
        input_tokens: Prompt tokens reported on the terminal chunk.
        output_tokens: Completion tokens reported on the terminal chunk.
        cost_per_mtok_in_usd: USD per 1M input tokens from the catalogue.
        cost_per_mtok_out_usd: USD per 1M output tokens from the catalogue.

    Returns:
        The combined USD cost of the turn.
    """
    return (
        input_tokens * cost_per_mtok_in_usd + output_tokens * cost_per_mtok_out_usd
    ) / _TOKENS_PER_MTOK
