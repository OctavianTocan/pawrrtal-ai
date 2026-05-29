"""Read-side CRUD over ``cost_ledger`` for the cost API.

Writes go through :class:`app.core.governance.cost_tracker.PostgresCostLedger`.
This module exposes the slow-path queries powering ``GET /api/v1/cost``:
window aggregate, per-model breakdown, raw row listing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models import CostLedger

DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 1000


async def list_cost_rows_for_user(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
    limit: int = DEFAULT_LIST_LIMIT,
    offset: int = 0,
) -> Sequence[CostLedger]:
    """Newest-first slice of one user's spend rows."""
    capped_limit = min(max(1, limit), MAX_LIST_LIMIT)
    stmt = (
        select(CostLedger)
        .where(CostLedger.user_id == user_id)
        .order_by(CostLedger.created_at.desc())
        .limit(capped_limit)
        .offset(max(0, offset))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def cumulative_window_usd(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
    window_hours: int,
) -> float:
    """Sum of ``cost_usd`` for ``user_id`` inside the rolling window."""
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    stmt = select(func.coalesce(func.sum(CostLedger.cost_usd), 0.0)).where(
        CostLedger.user_id == user_id,
        CostLedger.created_at >= cutoff,
    )
    result = await session.execute(stmt)
    value = result.scalar_one()
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def per_model_breakdown(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
    window_hours: int,
) -> list[dict[str, Any]]:
    """Per-model spend + turn-count rollup over the rolling window."""
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    stmt = (
        select(
            CostLedger.model_id,
            func.coalesce(func.sum(CostLedger.cost_usd), 0.0).label("cost_usd"),
            func.count().label("turns"),
        )
        .where(
            CostLedger.user_id == user_id,
            CostLedger.created_at >= cutoff,
        )
        .group_by(CostLedger.model_id)
        .order_by(func.sum(CostLedger.cost_usd).desc())
    )
    result = await session.execute(stmt)
    return [
        {
            "model_id": row.model_id,
            "cost_usd": float(row.cost_usd),
            "turns": int(row.turns),
        }
        for row in result.all()
    ]
