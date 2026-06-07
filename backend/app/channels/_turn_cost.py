"""Per-turn cost-ledger write — extracted from ``turn_orchestrator``.

Keeps ``app.channels.turn_orchestrator`` under the 500-line module budget
while keeping the cost-ledger write tightly bound to the turn lifecycle
(same DB session as the assistant-message persist so a failed commit
leaves no orphaned ledger row).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.aggregator import ChatTurnAggregator
from app.governance.cost_tracker import (
    PostgresCostLedger,
    record_turn_cost,
)
from app.infrastructure.config import settings
from app.providers.model_id import parse_model_id

logger = logging.getLogger(__name__)


async def record_turn_cost_if_enabled(
    *,
    session: AsyncSession,
    aggregator: ChatTurnAggregator,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    model_id: str,
    surface: str,
    log_tag: str,
) -> None:
    """Append the turn's spend to ``cost_ledger`` (PR 04).

    No-op when cost tracking is disabled or the aggregator saw zero
    usage events (early failures, errors before the terminal turn).
    Catches and logs DB errors so a ledger write failure never leaves
    the assistant row unpersisted — the caller commits in the same
    transaction.

    Pass plain values rather than a ``ChatTurnInput`` so this module
    has no import dependency on ``turn_orchestrator`` (sentrux disallows the
    cycle, even via ``TYPE_CHECKING``).
    """
    if not settings.cost_tracker_enabled:
        return
    if (
        aggregator.total_input_tokens <= 0
        and aggregator.total_output_tokens <= 0
        and aggregator.total_cost_usd <= 0
    ):
        return
    try:
        provider_slug = parse_model_id(model_id).host.value if model_id else "unknown"
    except Exception:
        provider_slug = "unknown"
    ledger = PostgresCostLedger(session=session)
    try:
        await record_turn_cost(
            ledger,
            user_id=user_id,
            conversation_id=conversation_id,
            provider=provider_slug,
            model_id=model_id,
            input_tokens=aggregator.total_input_tokens,
            output_tokens=aggregator.total_output_tokens,
            cost_usd=aggregator.total_cost_usd,
            surface=surface,
        )
    except Exception:
        logger.exception(
            "%s_COST_LEDGER_ERR conversation_id=%s",
            log_tag,
            conversation_id,
        )
