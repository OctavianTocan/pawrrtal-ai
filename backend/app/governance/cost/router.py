"""Cost API — read-only views over the per-user spend ledger.

Routes
------
* ``GET /api/v1/cost``         — aggregate summary for the rolling
  window the cost-budget middleware enforces against.
* ``GET /api/v1/cost/ledger``  — paginated raw rows, newest first.

Both routes are user-scoped via :func:`app.users.get_allowed_user`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.cost.crud import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    cumulative_window_usd,
    list_cost_rows_for_user,
    per_model_breakdown,
)
from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User, get_async_session
from app.schemas import CostLedgerRead, CostSummaryRead

# Upper bound on the configurable window so the SQL aggregate stays
# bounded.  90 days mirrors the default audit retention.
MAX_SUMMARY_WINDOW_HOURS = 90 * 24


def get_cost_router() -> APIRouter:
    """Build the cost-API router mounted at ``/api/v1/cost``."""
    router = APIRouter(prefix="/api/v1/cost", tags=["cost"])

    @router.get("/")
    async def cost_summary(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
        window_hours: int | None = Query(default=None, ge=1, le=MAX_SUMMARY_WINDOW_HOURS),
        breakdown: bool = Query(default=False),
    ) -> CostSummaryRead:
        """Aggregate spend over the rolling window for the calling user.

        ``window_hours`` defaults to ``settings.cost_reset_window_hours``
        so the API agrees with the gate enforcing the cap. ``breakdown=True``
        adds a per-model rollup for the same window.
        """
        effective_window = window_hours or int(settings.cost_reset_window_hours)
        cumulative = await cumulative_window_usd(
            user_id=user.id,
            session=session,
            window_hours=effective_window,
        )
        limit_usd = (
            float(settings.cost_max_per_user_daily_usd)
            if settings.cost_max_per_user_daily_usd > 0
            else None
        )
        remaining = max(0.0, limit_usd - cumulative) if limit_usd is not None else None
        per_model = (
            await per_model_breakdown(
                user_id=user.id,
                session=session,
                window_hours=effective_window,
            )
            if breakdown
            else None
        )
        return CostSummaryRead(
            window_hours=effective_window,
            current_usd=round(cumulative, 4),
            limit_usd=limit_usd,
            remaining_usd=remaining,
            per_model=per_model,
        )

    @router.get("/ledger", response_model=list[CostLedgerRead])
    async def cost_ledger(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
        limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
        offset: int = Query(default=0, ge=0),
    ) -> list[CostLedgerRead]:
        """Newest-first list of raw spend rows for the calling user."""
        rows = await list_cost_rows_for_user(
            user_id=user.id,
            session=session,
            limit=limit,
            offset=offset,
        )
        return [CostLedgerRead.model_validate(row) for row in rows]

    return router
