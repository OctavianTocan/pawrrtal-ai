import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.config import settings
from app.core.plugins.types import PreTurnHookContext
from app.core.providers.factory import resolve_llm
from app.core.tools.lcm_grep_agent import make_lcm_grep_tool
from app.core.tools.lcm_search_agent import make_lcm_search_tool
from app.core.tools.workspace_files import make_list_dir_tool, make_read_file_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are the Active Recall Agent running as a pre-turn hook for a personal AI assistant.
Your job is to search the conversation history and workspace memory for context relevant to the user's question before the main agent runs.

Instructions:
1. Role: Search conversation history and workspace files for relevant context (preferences, projects, past decisions, domain knowledge, people).
2. Output: Return EITHER a single, highly-compressed summary (max 600 characters) of relevant context, or the literal string "NONE".
3. Style: No preamble (do not say "Here is the context"). Output only the raw context or "NONE". Be extremely concise.
4. Tools: Use search/grep/file tools efficiently. Stop as soon as you have enough context.
"""


@dataclass
class _StreamTelemetry:
    parts: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error_msg: str | None = None


def _apply_stream_event(tel: _StreamTelemetry, event: dict[str, Any]) -> None:
    """Apply a single stream event to the running telemetry accumulator."""
    event_type = event.get("type")

    if event_type == "delta":
        chunk = event.get("content") or ""
        if chunk:
            tel.parts.append(chunk)
        return

    if event_type == "tool_use":
        tel.tools_called.append(event.get("name") or "unknown")
        return

    if event_type == "usage":
        tel.input_tokens += event.get("input_tokens", 0)
        tel.output_tokens += event.get("output_tokens", 0)
        tel.cost_usd += event.get("cost_usd", 0.0)
        return

    if event_type == "error":
        tel.error_msg = event.get("content")
        return

    if event_type == "agent_terminated":
        tel.error_msg = f"agent_terminated: {event.get('content')}"


async def _collect_stream_telemetry(
    stream: AsyncIterator[Any],
) -> tuple[str, list[str], int, int, float, str | None]:
    """Consume provider stream, aggregate text, and collect wide-event telemetry."""
    tel = _StreamTelemetry()
    async for event in stream:
        _apply_stream_event(tel, event)

    return (
        "".join(tel.parts).strip(),
        tel.tools_called,
        tel.input_tokens,
        tel.output_tokens,
        tel.cost_usd,
        tel.error_msg,
    )


async def run_active_recall(ctx: PreTurnHookContext) -> str | None:
    """Search LCM for context relevant to the user's question before the main agent turn."""
    if settings.lcm_enabled is False:
        logger.info(
            "ACTIVE_RECALL_SKIP conversation_id=%s reason=disabled",
            ctx.conversation_id,
        )
        return None

    start_time = time.perf_counter()
    tools_called: list[str] = []
    input_tokens = 0
    output_tokens = 0
    cost_usd = 0.0

    try:
        logger.info(
            "ACTIVE_RECALL_START conversation_id=%s user_id=%s",
            ctx.conversation_id,
            ctx.user_id,
        )
        # We're using a very fast, very cheap Google AI model to do the heavy lifting of the search.
        provider = resolve_llm("google-ai:google/gemini-3.1-flash-lite-preview")
        # We give the agent its tools.
        lcm_tools: list[AgentTool] = [
            make_lcm_grep_tool(conversation_id=ctx.conversation_id),
            make_lcm_search_tool(conversation_id=ctx.conversation_id),
            make_read_file_tool(ctx.workspace_root),
            make_list_dir_tool(ctx.workspace_root),
        ]

        stream = provider.stream(
            question=ctx.question,
            conversation_id=uuid.uuid4(),  # isolated; not a real turn TODO: This should be easier to do. (Making a subagent that doesn't use real turns).
            user_id=ctx.user_id,
            history=None,
            tools=lcm_tools,
            system_prompt=SYSTEM_PROMPT,
        )

        (
            answer,
            tools_called,
            input_tokens,
            output_tokens,
            cost_usd,
            error_msg,
        ) = await _collect_stream_telemetry(stream)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        tools_str = ",".join(tools_called) or "none"

        if error_msg:
            logger.warning(
                "ACTIVE_RECALL_OUT conversation_id=%s user_id=%s status=error "
                "duration_ms=%.1f tools_called=[%s] input_tokens=%d output_tokens=%d cost_usd=%.6f error=%s",
                ctx.conversation_id,
                ctx.user_id,
                duration_ms,
                tools_str,
                input_tokens,
                output_tokens,
                cost_usd,
                error_msg,
            )
            return f"active_recall: expansion call failed — {error_msg}"

        if not answer:
            logger.info(
                "ACTIVE_RECALL_OUT conversation_id=%s user_id=%s status=empty "
                "duration_ms=%.1f tools_called=[%s] input_tokens=%d output_tokens=%d cost_usd=%.6f",
                ctx.conversation_id,
                ctx.user_id,
                duration_ms,
                tools_str,
                input_tokens,
                output_tokens,
                cost_usd,
            )
            return "active_recall: the model returned an empty response."

        logger.info(
            "ACTIVE_RECALL_OUT conversation_id=%s user_id=%s status=success "
            "duration_ms=%.1f tools_called=[%s] input_tokens=%d output_tokens=%d cost_usd=%.6f result_len=%d",
            ctx.conversation_id,
            ctx.user_id,
            duration_ms,
            tools_str,
            input_tokens,
            output_tokens,
            cost_usd,
            len(answer),
        )
        # Intentionally mentioning the active recall agent in the response so the assistant knows where it came from.
        return f"Here's some context that your Active Recall agent found: {answer}"

    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        tools_str = ",".join(tools_called) or "none"
        logger.exception(
            "ACTIVE_RECALL_OUT conversation_id=%s user_id=%s status=failed "
            "duration_ms=%.1f tools_called=[%s] input_tokens=%d output_tokens=%d cost_usd=%.6f",
            ctx.conversation_id,
            ctx.user_id,
            duration_ms,
            tools_str,
            input_tokens,
            output_tokens,
            cost_usd,
        )
        return f"active_recall: expansion call failed — {exc}"
