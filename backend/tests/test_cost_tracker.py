"""Tests for ``app.core.governance.cost_tracker``.

Covers the cost-rate computation, the ledger record/aggregate path,
and the per-request reservation defaults.  ``CostBudget`` itself is
just a frozen dataclass so it doesn't get its own test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.governance.cost_tracker import (
    TOKENS_PER_MTOK,
    CostBudget,
    PostgresCostLedger,
    compute_cost_usd,
    per_request_reservation_usd,
    record_turn_cost,
)
from app.core.providers.catalog import ModelEntry
from app.core.providers.model_id import Host, Vendor
from app.infrastructure.database.legacy import User
from app.models import CostLedger

pytestmark = pytest.mark.anyio


def _entry(in_rate: float, out_rate: float) -> ModelEntry:
    return ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="test-model",
        display_name="Test",
        short_name="Test",
        description="x",
        is_default=False,
        cost_per_mtok_in_usd=in_rate,
        cost_per_mtok_out_usd=out_rate,
    )


class TestComputeCostUsd:
    def test_returns_fallback_when_provided(self) -> None:
        out = compute_cost_usd(
            catalog_entry=_entry(3.0, 15.0),
            input_tokens=1_000,
            output_tokens=500,
            fallback_usd=0.05,
        )
        # Fallback wins over computed value (Claude path).
        assert out == 0.05

    def test_zero_fallback_uses_catalog_rates(self) -> None:
        out = compute_cost_usd(
            catalog_entry=_entry(3.0, 15.0),
            input_tokens=TOKENS_PER_MTOK,  # 1M input tokens
            output_tokens=TOKENS_PER_MTOK,  # 1M output tokens
        )
        # 1M * $3 + 1M * $15 = $18.
        assert out == pytest.approx(18.0)

    def test_no_catalog_entry_returns_fallback(self) -> None:
        assert (
            compute_cost_usd(
                catalog_entry=None,
                input_tokens=100,
                output_tokens=200,
                fallback_usd=0.0,
            )
            == 0.0
        )

    def test_zero_rates_returns_fallback(self) -> None:
        assert (
            compute_cost_usd(
                catalog_entry=_entry(0.0, 0.0),
                input_tokens=100,
                output_tokens=200,
                fallback_usd=0.0,
            )
            == 0.0
        )


class TestPerRequestReservation:
    def test_caps_at_per_request_when_low(self) -> None:
        budget = CostBudget(
            max_per_request_usd=0.01,
            max_per_user_window_usd=10.0,
            window_hours=24,
        )
        # Small per-request cap clamps the reservation.
        assert per_request_reservation_usd(budget) == 0.01

    def test_default_when_no_per_request_cap(self) -> None:
        budget = CostBudget(
            max_per_request_usd=0.0,
            max_per_user_window_usd=10.0,
            window_hours=24,
        )
        assert per_request_reservation_usd(budget) > 0


class TestPostgresCostLedger:
    async def test_record_and_aggregate(self, db_session: AsyncSession, test_user: User) -> None:
        ledger = PostgresCostLedger(session=db_session)

        await record_turn_cost(
            ledger,
            user_id=test_user.id,
            conversation_id=None,
            provider="google_ai",
            model_id="google_ai:google/gemini-3-flash-preview",
            input_tokens=1_000,
            output_tokens=500,
            cost_usd=0.012,
            surface="web",
        )
        await record_turn_cost(
            ledger,
            user_id=test_user.id,
            conversation_id=None,
            provider="google_ai",
            model_id="google_ai:google/gemini-3-flash-preview",
            input_tokens=2_000,
            output_tokens=1_000,
            cost_usd=0.024,
            surface="web",
        )
        await db_session.commit()

        cumulative = await ledger.cumulative_window_usd(user_id=test_user.id, window_hours=24)
        assert cumulative == pytest.approx(0.036)

    async def test_zero_cost_zero_tokens_skipped(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """``record_turn_cost`` is a no-op when the turn produced no usage."""
        ledger = PostgresCostLedger(session=db_session)
        await record_turn_cost(
            ledger,
            user_id=test_user.id,
            conversation_id=None,
            provider="google_ai",
            model_id="google_ai:google/gemini-3-flash-preview",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            surface=None,
        )
        await db_session.commit()
        rows = await db_session.execute(
            CostLedger.__table__.select().where(CostLedger.user_id == test_user.id)
        )
        assert rows.scalars().all() == []

    async def test_window_excludes_old_rows(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Rows older than ``window_hours`` are excluded from the aggregate."""
        ledger = PostgresCostLedger(session=db_session)
        # Record one row with an older timestamp by setting it directly.
        old_row = CostLedger(
            id=uuid.uuid4(),
            user_id=test_user.id,
            conversation_id=None,
            provider="google_ai",
            model_id="google_ai:google/gemini-3-flash-preview",
            input_tokens=10_000,
            output_tokens=10_000,
            cost_usd=5.00,
            surface="web",
            created_at=datetime.now(UTC) - timedelta(hours=72),
        )
        db_session.add(old_row)
        await record_turn_cost(
            ledger,
            user_id=test_user.id,
            conversation_id=None,
            provider="google_ai",
            model_id="google_ai:google/gemini-3-flash-preview",
            input_tokens=100,
            output_tokens=100,
            cost_usd=0.01,
            surface="web",
        )
        await db_session.commit()

        # 24h window only sees the recent row.
        recent = await ledger.cumulative_window_usd(user_id=test_user.id, window_hours=24)
        assert recent == pytest.approx(0.01)
        # 7d window sees both.
        wide = await ledger.cumulative_window_usd(user_id=test_user.id, window_hours=24 * 7)
        assert wide == pytest.approx(5.01)
