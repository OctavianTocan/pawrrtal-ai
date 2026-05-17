"""CRUD over ``audit_events``.

Read-only from the user's perspective — audit rows are append-only and
no application code ever updates them. The retention purge (called
from the scheduler lifespan, PR 12) is the only path that deletes
rows, and it deletes whole rows by age, never edits.

Writes go through :class:`app.core.governance.audit.AuditLogger`. This
module only exposes list/get/dashboard queries.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent

# Hard cap on the list endpoint to keep responses bounded.
MAX_LIST_LIMIT = 1000
DEFAULT_LIST_LIMIT = 100
DEFAULT_DASHBOARD_WINDOW_HOURS = 24


async def list_audit_events_for_user(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
    limit: int = DEFAULT_LIST_LIMIT,
    offset: int = 0,
    event_type: str | None = None,
    since: datetime | None = None,
) -> Sequence[AuditEvent]:
    """Most-recent-first slice of one user's audit events."""
    capped_limit = min(max(1, limit), MAX_LIST_LIMIT)
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.user_id == user_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(capped_limit)
        .offset(max(0, offset))
    )
    if event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if since is not None:
        stmt = stmt.where(AuditEvent.created_at >= since)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_recent_violations(
    *,
    session: AsyncSession,
    user_id: uuid.UUID | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
) -> Sequence[AuditEvent]:
    """Most-recent ``security_violation`` rows, optionally scoped to a user."""
    capped_limit = min(max(1, limit), MAX_LIST_LIMIT)
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.event_type == "security_violation")
        .order_by(AuditEvent.created_at.desc())
        .limit(capped_limit)
    )
    if user_id is not None:
        stmt = stmt.where(AuditEvent.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_activity_summary(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
    hours: int = DEFAULT_DASHBOARD_WINDOW_HOURS,
) -> dict[str, Any]:
    """Aggregate counts for one user over the past ``hours``."""
    since = datetime.now(UTC) - timedelta(hours=hours)

    # Counts grouped by event_type
    type_rows = await session.execute(
        select(AuditEvent.event_type, func.count())
        .where(AuditEvent.user_id == user_id, AuditEvent.created_at >= since)
        .group_by(AuditEvent.event_type)
    )
    by_type: dict[str, int] = {row[0]: row[1] for row in type_rows.all()}

    # Counts grouped by risk_level
    risk_rows = await session.execute(
        select(AuditEvent.risk_level, func.count())
        .where(AuditEvent.user_id == user_id, AuditEvent.created_at >= since)
        .group_by(AuditEvent.risk_level)
    )
    by_risk: dict[str, int] = {row[0]: row[1] for row in risk_rows.all()}

    # Success / total
    totals = await session.execute(
        select(
            func.count().label("total"),
            func.count().filter(AuditEvent.success.is_(True)).label("successes"),
        ).where(AuditEvent.user_id == user_id, AuditEvent.created_at >= since)
    )
    total_row = totals.first()
    total = int(total_row.total) if total_row else 0
    successes = int(total_row.successes) if total_row else 0
    success_rate = (successes / total) if total > 0 else 0.0

    return {
        "user_id": str(user_id),
        "window_hours": hours,
        "total_events": total,
        "success_rate": round(success_rate, 4),
        "by_type": by_type,
        "by_risk": by_risk,
    }


async def purge_expired_audit_events(
    *,
    session: AsyncSession,
    retention_days: int,
) -> int:
    """Delete audit rows older than ``retention_days``.

    Returns the rowcount. Zero or negative ``retention_days`` is a
    no-op so the scheduler can disable the purge by setting
    ``settings.audit_log_retention_days = 0``.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await session.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff))
    await session.commit()
    # DML ``execute`` returns a ``CursorResult`` with ``rowcount``; the
    # statically-declared ``Result`` base doesn't expose it.
    rowcount: int = getattr(result, "rowcount", 0)
    return rowcount or 0
