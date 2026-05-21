import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.config import settings
from app.core.plugins.types import PreTurnHookContext
from app.core.providers.factory import resolve_llm
from app.core.tools.lcm_grep_agent import make_lcm_grep_tool
from app.core.tools.lcm_search_agent import make_lcm_search_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You search long-term conversation memory. Return EITHER a single short summary (<=600 chars) of context relevant to the user message OR the literal string NONE. No preamble.
"""


async def _collect_stream_telemetry(
    stream: AsyncIterator[Any],
) -> tuple[str, list[str], int, int, float, str | None]:
    """Consume provider stream, aggregate text, and collect wide-event telemetry."""
    parts: list[str] = []
    tools_called: list[str] = []
    input_tokens = 0
    output_tokens = 0
    cost_usd = 0.0
    error_msg: str | None = None

    async for event in stream:
        event_type = event.get("type")
        if event_type == "delta":
            chunk = event.get("content") or ""
            if chunk:
                parts.append(chunk)
        elif event_type == "tool_use":
            tool_name = event.get("name") or "unknown"
            tools_called.append(tool_name)
        elif event_type == "usage":
            input_tokens += event.get("input_tokens", 0)
            output_tokens += event.get("output_tokens", 0)
            cost_usd += event.get("cost_usd", 0.0)
        elif event_type == "error":
            error_msg = event.get("content")
        elif event_type == "agent_terminated":
            error_msg = f"agent_terminated: {event.get('content')}"

    return (
        "".join(parts).strip(),
        tools_called,
        input_tokens,
        output_tokens,
        cost_usd,
        error_msg,
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

        # TODO: This needs to be passed through the ctx, so that we can support searching for the user's memory. (Without LCM).
        search_prompt = f"Search the conversation history using your LCM tools for context relevant to the user's question: {ctx.question}"

        # The set of tools, restricted to LCM only.
        lcm_tools: list[AgentTool] = [
            make_lcm_grep_tool(conversation_id=ctx.conversation_id),
            make_lcm_search_tool(conversation_id=ctx.conversation_id),
        ]

        stream = provider.stream(
            question=search_prompt,
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
            return f"lcm_expand_query: expansion call failed — {error_msg}"

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
            return "lcm_expand_query: the model returned an empty response."

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
        return answer

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
        return f"lcm_expand_query: expansion call failed — {exc}"
