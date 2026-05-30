"""Per-turn cost ledger + per-user / per-window budget gate.

Two-tier cost control mirroring CCT:

1. **Per-request cap** (``cost_max_per_request_usd``) — passed straight
   to the Claude SDK as ``max_budget_usd``; mirrored for non-SDK
   providers via the agent-loop pre-turn safety check (PR 04b lands
   the loop side; the Claude SDK side ships in this PR).
2. **Per-user cumulative cap** (``cost_max_per_user_daily_usd``) —
   enforced by :class:`CostBudgetMiddleware` before the chat handler
   even resolves the provider.  Sums every row in ``cost_ledger`` for
   the user inside the rolling window and refuses with HTTP 402 when
   adding the configured request reservation would exceed the cap.

The ``CostLedgerStorage`` protocol mirrors the rate-limiter's
``RateLimitStorage`` so a future Redis swap covers both surfaces with
the same change.  The default :class:`PostgresCostLedger` writes to
the ``cost_ledger`` table introduced in migration 012.

Usage from the chat router (PR 04 wire-up)::

    from app.governance.cost_tracker import (
        CostBudget,
        PostgresCostLedger,
        compute_cost_usd,
        record_turn_cost,
    )

    ledger = PostgresCostLedger(session)
    await record_turn_cost(
        ledger,
        user_id=user.id,
        conversation_id=conversation.id,
        provider=parsed_model.host.value,
        model_id=model_id,
        input_tokens=aggregator.total_input_tokens,
        output_tokens=aggregator.total_output_tokens,
        cost_usd=aggregator.total_cost_usd,
        surface=surface,
    )
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models import CostLedger
from app.providers.catalog import ModelEntry

logger = logging.getLogger(__name__)

# 1M tokens — the unit our catalog publishes per-token rates against.
# Named so the multiplication site reads as a unit conversion, not a
# magic number.
TOKENS_PER_MTOK = 1_000_000


@dataclass(frozen=True)
class CostBudget:
    """Two-tier cost cap configuration.

    Built once per process from :class:`Settings` and passed into the
    middleware + provider construction; both fields ``0`` disable the
    matching cap.
    """

    max_per_request_usd: float
    max_per_user_window_usd: float
    window_hours: int


class CostLedgerStorage(Protocol):
    """Storage seam so the chat router never imports SQLAlchemy directly.

    Mirrors :class:`app.infrastructure.middleware.rate_limit.RateLimitStorage` so a future
    Redis-backed implementation slots in without touching the chat
    router or middleware.
    """

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        provider: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        surface: str | None,
    ) -> None:
        """Append one turn's spend row to the ledger."""
        ...

    async def cumulative_window_usd(
        self,
        *,
        user_id: uuid.UUID,
        window_hours: int,
    ) -> float:
        """Sum of ``cost_usd`` for ``user_id`` over the last ``window_hours``."""
        ...


@dataclass
class PostgresCostLedger(CostLedgerStorage):
    """SQLAlchemy-backed :class:`CostLedgerStorage` for the chat router."""

    session: AsyncSession

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        provider: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        surface: str | None,
    ) -> None:
        """Insert one row into ``cost_ledger`` (caller commits)."""
        row = CostLedger(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conversation_id,
            provider=provider,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            surface=surface,
            created_at=datetime.now(UTC),
        )
        self.session.add(row)

    async def cumulative_window_usd(
        self,
        *,
        user_id: uuid.UUID,
        window_hours: int,
    ) -> float:
        """Aggregate spend in the rolling window via SQL ``SUM``."""
        cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
        stmt = select(func.coalesce(func.sum(CostLedger.cost_usd), 0.0)).where(
            CostLedger.user_id == user_id,
            CostLedger.created_at >= cutoff,
        )
        result = await self.session.execute(stmt)
        value = result.scalar_one()
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


def compute_cost_usd(
    *,
    catalog_entry: ModelEntry | None,
    input_tokens: int,
    output_tokens: int,
    fallback_usd: float = 0.0,
) -> float:
    """Convert token counts into a USD figure using the catalog rates.

    Used by the Gemini provider (PR 04b) which doesn't get a
    Claude-style ``total_cost_usd`` from its SDK.  When ``fallback_usd``
    is non-zero (Claude path) it wins — Anthropic's reported figure is
    authoritative.

    Returns ``fallback_usd`` when:

    * ``catalog_entry`` is ``None`` (model not in our catalog), or
    * the catalog entry has both rates set to ``0.0`` (cost unknown).
    """
    if fallback_usd > 0:
        return fallback_usd
    if catalog_entry is None:
        return fallback_usd
    in_rate = catalog_entry.cost_per_mtok_in_usd
    out_rate = catalog_entry.cost_per_mtok_out_usd
    if in_rate <= 0 and out_rate <= 0:
        return fallback_usd
    return (input_tokens * in_rate + output_tokens * out_rate) / TOKENS_PER_MTOK


async def record_turn_cost(
    storage: CostLedgerStorage,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    provider: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    surface: str | None,
) -> None:
    """Append one turn's spend to the ledger.

    Thin wrapper over the storage so callers don't need to know which
    backend they're talking to.  No-op when both token counts and the
    cost are zero (saves ledger churn for early-failure turns).
    """
    if input_tokens <= 0 and output_tokens <= 0 and cost_usd <= 0:
        return
    await storage.record(
        user_id=user_id,
        conversation_id=conversation_id,
        provider=provider,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        surface=surface,
    )


# Pre-flight reservation used by :class:`CostBudgetMiddleware`. We
# don't know the cost of the current turn yet (it depends on the
# model + request length + tool decisions), so we reserve a small
# headroom that's usually enough to cover an above-average turn. The
# real cost is recorded *after* the turn completes; this reservation
# is only used to short-circuit obvious-busted budgets up front.
_DEFAULT_PER_REQUEST_RESERVATION_USD = 0.10


# Type alias for the storage factory the middleware accepts.  Lets
# tests inject an in-memory stub without touching the DB.
CostStorageFactory = (
    Callable[[AsyncSession], Awaitable[CostLedgerStorage]]
    | Callable[[AsyncSession], CostLedgerStorage]
)


def per_request_reservation_usd(budget: CostBudget) -> float:
    """Conservative pre-flight reservation for the per-window check.

    Caps at ``budget.max_per_request_usd`` when set so a low per-request
    cap also lowers the reservation; defaults to a small fixed fraction
    of a dollar otherwise.
    """
    if budget.max_per_request_usd > 0:
        return min(budget.max_per_request_usd, _DEFAULT_PER_REQUEST_RESERVATION_USD)
    return _DEFAULT_PER_REQUEST_RESERVATION_USD
