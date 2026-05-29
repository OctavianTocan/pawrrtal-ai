"""Pre-flight cost-budget enforcement for ``/api/v1/chat``.

Extracted from :mod:`app.chat.router` to keep that module's fan-out
under the sentrux god-file threshold. The cost-tracker integration
adds ``CostBudget``, ``PostgresCostLedger``, and
``per_request_reservation_usd`` — three names from one module
that are only used by the gate function below. Hoisting them here
collapses chat.py's edge count by one (it now imports a single
function from this file instead of pulling the three names plus
``settings.cost_tracker_enabled`` apart on its own).
"""

from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.governance.cost_tracker import (
    CostBudget,
    PostgresCostLedger,
    per_request_reservation_usd,
)

logger = logging.getLogger(__name__)


async def enforce_cost_budget(
    *,
    user_id: object,
    session: AsyncSession,
    rid: str,
) -> None:
    """Pre-flight per-user cost cap.

    Called at the top of the chat handler so a denied request never
    pays for tool composition or provider resolution. Fails OPEN on
    DB errors — the gate is a soft control and the Claude SDK's
    per-request ``max_budget_usd`` still bounds the worst case.
    """
    if not settings.cost_tracker_enabled:
        return
    if settings.cost_max_per_user_daily_usd <= 0:
        return

    budget = CostBudget(
        max_per_request_usd=float(settings.cost_max_per_request_usd),
        max_per_user_window_usd=float(settings.cost_max_per_user_daily_usd),
        window_hours=int(settings.cost_reset_window_hours),
    )
    ledger = PostgresCostLedger(session=session)
    try:
        cumulative = await ledger.cumulative_window_usd(
            user_id=user_id,  # type: ignore[arg-type]
            window_hours=budget.window_hours,
        )
    except Exception:
        logger.exception("CHAT_COST_LOOKUP_FAILED rid=%s user_id=%s", rid, user_id)
        return
    reservation = per_request_reservation_usd(budget)
    if cumulative + reservation <= budget.max_per_user_window_usd:
        return
    remaining = max(0.0, budget.max_per_user_window_usd - cumulative)
    logger.info(
        "CHAT_COST_DENIED rid=%s user_id=%s cumulative=%.4f limit=%.4f window_hours=%d",
        rid,
        user_id,
        cumulative,
        budget.max_per_user_window_usd,
        budget.window_hours,
    )
    raise HTTPException(
        status_code=402,
        detail={
            "message": (
                f"Cost budget exhausted: ${cumulative:.4f} of "
                f"${budget.max_per_user_window_usd:.2f} used in the last "
                f"{budget.window_hours} hours."
            ),
            "remaining_usd": round(remaining, 4),
            "current_usd": round(cumulative, 4),
            "limit_usd": budget.max_per_user_window_usd,
            "window_hours": budget.window_hours,
        },
    )
