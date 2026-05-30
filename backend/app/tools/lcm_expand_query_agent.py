"""Agent-loop adapter for the LCM expand_query tool (PR #6).

Exposes :func:`make_lcm_expand_query_tool` which returns an
:class:`AgentTool` for deep recall over the full conversation history.

Usage::

    from app.tools.lcm_expand_query_agent import make_lcm_expand_query_tool

    if settings.lcm_enabled:
        tools.append(
            make_lcm_expand_query_tool(
                conversation_id=conv.id,
                user_id=user.id,
                model_id=model_id,
            )
        )
"""

from __future__ import annotations

import uuid
from typing import Any

from app.agents.types import AgentTool
from app.infrastructure.database.legacy import async_session_maker
from app.tools.display import make_tool_display, summarize_query
from app.tools.lcm_expand_query import lcm_expand_query

_TOOL_NAME = "lcm_expand_query"

_TOOL_DESCRIPTION = (
    "Answer a question by reading the FULL conversation history — including"
    " all compacted summary nodes AND raw messages — with a dedicated LLM call."
    "  Use this when lcm_grep found a relevant excerpt but you need the complete"
    " story, or when the answer likely spans multiple compacted nodes and a"
    " summary cannot give you enough detail."
    "  This tool makes an extra LLM call, so prefer lcm_grep or lcm_describe"
    " for simple lookups."
    "  Tip: be specific in your prompt — the better the question, the better"
    " the answer."
)

_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": (
                "The question or retrieval task to answer from the full"
                " conversation history.  Be specific: include key terms,"
                " names, or topics relevant to what you're looking for."
            ),
        },
    },
    "required": ["prompt"],
}


def make_lcm_expand_query_tool(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    model_id: str,
) -> AgentTool:
    """Return an :class:`AgentTool` wrapping the LCM deep-recall expansion.

    Args:
        conversation_id: The conversation to expand.  Baked in so the
            agent cannot query other conversations.
        user_id: Used to resolve provider API keys for the expansion call.
        model_id: Default model for the expansion call.  May be overridden
            by ``settings.lcm_summary_model`` if set.

    Returns:
        A configured :class:`AgentTool` ready for the tools list.
    """

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        prompt = str(kwargs.get("prompt") or "")
        async with async_session_maker() as session:
            return await lcm_expand_query(
                session,
                conversation_id=conversation_id,
                user_id=user_id,
                model_id=model_id,
                prompt=prompt,
            )

    return AgentTool(
        name=_TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        parameters=_PARAMETERS,
        execute=_execute,
        display=make_tool_display(
            icon="🧠",
            label="Expand memory query",
            present=lambda args: (
                f"🧠 Expanding memory query for {summarize_query(args.get('prompt'))}"
            ),
            compact=lambda args: f"Expand memory query -> {summarize_query(args.get('prompt'))}",
        ),
    )
