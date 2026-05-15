"""Audit-log wrapper for Notion tool calls.

Every ``notion_*`` tool runs its underlying work through
:func:`with_audit`, which times the call, captures the request/response
shape, and writes one row to :class:`app.models.NotionOperationLog`.
Failures are logged with the error string instead of the response, so
the ``notion_logs_read`` tool can answer "what's been failing lately?"
without forcing every tool to remember the same boilerplate.

The wrapper is intentionally tiny: it adds *only* audit logging.  Token
isolation, subprocess management, and JSON parsing belong in
``ntn_client``; tool-specific shaping belongs in the per-tool factory.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.db import async_session_maker
from app.integrations.notion.ntn_client import NtnError
from app.models import NotionOperationLog

logger = logging.getLogger(__name__)

# Status strings stored in NotionOperationLog.status — kept narrow so
# log-reader prompts can match against a literal union.
STATUS_OK = "ok"
STATUS_ERROR = "error"

# Hard cap on stored JSON payload size, in bytes after serialisation.
# Notion responses can be enormous (a full database query), and we
# don't need them verbatim for debugging — a head-trimmed snapshot is
# plenty.
MAX_AUDIT_PAYLOAD_BYTES = 4096


async def with_audit(
    *,
    workspace_id: uuid.UUID,
    tool_name: str,
    operation: str,
    request: dict[str, Any] | None,
    func: Callable[[], Awaitable[Any]],
    page_id: str | None = None,
    database_id: str | None = None,
) -> Any:
    """Run ``func`` and write one audit row regardless of outcome.

    Args:
        workspace_id: The active workspace; rows cascade with its delete.
        tool_name: Name of the calling tool (e.g. ``"notion_search"``).
        operation: Coarse bucket — ``"search"``, ``"read"``, ``"write"``,
            etc.  Looser than ``tool_name`` so log-reader queries can
            slice across closely related tools.
        request: Arbitrary JSON-safe dict capturing the call's input.
            Pass ``None`` when the call has no meaningful input (e.g.
            ``notion_doctor``).
        func: Async function that performs the actual work and returns
            the value :func:`with_audit` should forward to the caller.
        page_id: Optional indexed column; set when the tool targets a
            specific Notion page so ``notion_logs_read`` can filter on it.
        database_id: Optional indexed column; set when the tool targets a
            specific Notion database.
        page_id / database_id: Optional indexed columns; set when the
            tool targets a specific Notion entity so ``notion_logs_read``
            can filter on them.

    Returns:
        Whatever ``func()`` returned, unchanged.

    Raises:
        The original exception from ``func()``, after a failure row is
        written.  We re-raise rather than swallow because the caller's
        tool contract expects to surface errors to the agent.
    """
    started_at = time.monotonic()
    try:
        result = await func()
    except NtnError as exc:
        await _persist(
            workspace_id=workspace_id,
            tool_name=tool_name,
            operation=operation,
            page_id=page_id,
            database_id=database_id,
            status=STATUS_ERROR,
            duration_ms=_elapsed_ms(started_at),
            error=str(exc),
            request_json=request,
            response_json=None,
        )
        raise
    except (TimeoutError, OSError) as exc:
        # ``asyncio.TimeoutError`` is ``TimeoutError`` since 3.11.  OS
        # errors cover the case where the binary is missing or the
        # subprocess setup itself failed.  Narrower than ``Exception``
        # so unrelated bugs aren't masked.
        await _persist(
            workspace_id=workspace_id,
            tool_name=tool_name,
            operation=operation,
            page_id=page_id,
            database_id=database_id,
            status=STATUS_ERROR,
            duration_ms=_elapsed_ms(started_at),
            error=str(exc),
            request_json=request,
            response_json=None,
        )
        raise

    await _persist(
        workspace_id=workspace_id,
        tool_name=tool_name,
        operation=operation,
        page_id=page_id,
        database_id=database_id,
        status=STATUS_OK,
        duration_ms=_elapsed_ms(started_at),
        error=None,
        request_json=request,
        response_json=_jsonable(result),
    )
    return result


def _elapsed_ms(started_at: float) -> int:
    """Return the elapsed wall-clock time since ``started_at`` in ms."""
    return int((time.monotonic() - started_at) * 1000)


def _jsonable(value: Any) -> Any:
    """Return a JSON-serializable snapshot of ``value`` for the log row.

    Falls back to ``str()`` on anything ``json`` rejects (e.g. raw bytes,
    custom dataclasses) so audit writes never crash on exotic returns.
    Truncates oversized payloads at :data:`MAX_AUDIT_PAYLOAD_BYTES`.
    """
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError):
        encoded = json.dumps(str(value))
    if len(encoded) > MAX_AUDIT_PAYLOAD_BYTES:
        # Store a string marker rather than truncated JSON, which would
        # corrupt the structured representation.
        return {
            "_truncated": True,
            "_size_bytes": len(encoded),
            "head": encoded[:MAX_AUDIT_PAYLOAD_BYTES],
        }
    return json.loads(encoded)


async def _persist(
    *,
    workspace_id: uuid.UUID,
    tool_name: str,
    operation: str,
    page_id: str | None,
    database_id: str | None,
    status: str,
    duration_ms: int,
    error: str | None,
    request_json: dict[str, Any] | None,
    response_json: Any | None,
) -> None:
    """Write one audit row in its own DB session.

    Uses a fresh session rather than the chat router's transactional
    one so an audit-log write never fails the actual tool call.  The
    write happens after the tool returns, so a failure here is logged
    but not propagated.
    """
    try:
        async with async_session_maker() as session:
            session.add(
                NotionOperationLog(
                    workspace_id=workspace_id,
                    tool_name=tool_name,
                    operation=operation,
                    page_id=page_id,
                    database_id=database_id,
                    status=status,
                    duration_ms=duration_ms,
                    error=error,
                    request_json=request_json,
                    response_json=response_json,
                    created_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.commit()
    except OSError as exc:
        # DB unreachable or disk full — log loudly but never block the
        # caller.  A missed audit row is not worth a failed tool turn.
        logger.warning(
            "notion_audit: failed to persist row tool=%s status=%s: %s",
            tool_name,
            status,
            exc,
        )
