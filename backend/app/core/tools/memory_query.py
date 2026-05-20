"""``memory_query`` AgentTool — read top-K proactive memories (#340).

Lets the agent pull the long tail of user preferences / project
decisions / feedback that the post-turn classifier wrote to the
``memories`` table. The system-prompt assembler already surfaces
the freshest top-N as context; this tool covers the cases where
the agent wants something older, narrower, or kind-filtered.

The tool is read-only — writes happen in the classifier hook.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.crud.memory import (
    MemoryKind,
    list_memories_for_user,
    mark_memory_referenced,
)
from app.db import async_session_maker

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 5
_MAX_LIMIT = 20
_ALLOWED_KINDS: tuple[MemoryKind, ...] = ("feedback", "project", "user")


def make_memory_query_tool(*, user_id: uuid.UUID) -> AgentTool:
    """Return the ``memory_query`` AgentTool bound to ``user_id``.

    The chat router builds one of these per turn (the user id is
    known once a request lands), then appends it to the agent's
    tool list. The tool ignores requests for memories belonging to
    other users — the binding here is the authorisation gate.

    Args:
        user_id: Authenticated Pawrrtal user the memory rows belong
            to. Stored in the closure so the model can never read
            another user's memories.

    Returns:
        An :class:`AgentTool` the agent can call mid-turn to pull
        the long tail of proactive memories the classifier wrote.
    """

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        kind_arg = kwargs.get("kind")
        kind: MemoryKind | None
        if isinstance(kind_arg, str) and kind_arg in _ALLOWED_KINDS:
            kind = kind_arg  # type: ignore[assignment]
        else:
            kind = None

        raw_limit = kwargs.get("limit", _DEFAULT_LIMIT)
        try:
            limit = max(1, min(_MAX_LIMIT, int(raw_limit)))
        except (TypeError, ValueError):
            limit = _DEFAULT_LIMIT

        async with async_session_maker() as session:
            rows = await list_memories_for_user(
                session,
                user_id,
                kind=kind,
                limit=limit,
            )
            for row in rows:
                # Mark each surfaced row as referenced so cleanup
                # jobs keep hot memories around. Fire-and-forget
                # within the same session — no separate commit.
                await mark_memory_referenced(session, row.id)

        if not rows:
            return _empty_response(kind=kind)
        return _format_memories(rows, kind=kind)

    return AgentTool(
        name="memory_query",
        description=(
            "Read the user's saved memories — user preferences, project "
            "decisions, and feedback the Paw kept from past turns. Use "
            "this when the user references something they told you "
            "earlier but it's not in the immediate context, or when "
            "you want to verify the user's standing preference before "
            "making an assumption."
        ),
        parameters={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": list(_ALLOWED_KINDS),
                    "description": (
                        "Filter by memory kind: ``feedback`` "
                        "(corrections / preferences on the Paw's "
                        "behaviour), ``project`` (architectural / "
                        "product decisions), or ``user`` (durable "
                        "user context). Omit to return all kinds."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _MAX_LIMIT,
                    "description": (
                        f"Maximum number of memories to return. "
                        f"Default {_DEFAULT_LIMIT}, capped at {_MAX_LIMIT}."
                    ),
                },
            },
            "required": [],
        },
        execute=execute,
    )


def _format_memories(rows: list[Any], *, kind: MemoryKind | None) -> str:
    """Render the memory rows as a model-readable bulleted list."""
    header = (
        f"Saved memories ({kind})" if kind is not None else "Saved memories (all kinds)"
    )
    lines = [header]
    for row in rows:
        timestamp = row.created_at.strftime("%Y-%m-%d") if row.created_at else "?"
        lines.append(f"- [{row.kind} · {timestamp}] {row.text}")
    return "\n".join(lines)


def _empty_response(*, kind: MemoryKind | None) -> str:
    """Render the "no memories yet" reply."""
    if kind is None:
        return "No saved memories yet."
    return f"No saved memories of kind '{kind}' yet."
