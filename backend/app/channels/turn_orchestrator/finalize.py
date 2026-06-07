"""Turn finalization and completion accounting."""

from __future__ import annotations

import logging
import time
import uuid
from collections import Counter

from sqlalchemy import exc as sa_exc

from app.channels._turn_cost import record_turn_cost_if_enabled
from app.chat.aggregator import ChatTurnAggregator
from app.conversations.messages_crud import finalize_assistant_message
from app.infrastructure.event_bus import TurnCompletedEvent, publish_if_available
from app.lcm import schedule_lcm_compaction

from .history import _turn_session
from .types import ChatTurnInput

logger = logging.getLogger(__name__)

_MS_PER_SECOND_FOR_LOG = 1000
_TTFT_LOG_MISSING = "-"


async def _finalize_turn(
    *,
    turn_input: ChatTurnInput,
    aggregator: ChatTurnAggregator,
    assistant_message_id: uuid.UUID,
    started_at: float,
    event_count: int,
    event_breakdown: Counter[str],
    ttft_ms: float | None,
) -> None:
    """Patch the assistant placeholder with the final aggregated stream state.

    The two writes (message finalize + cost ledger) are split across
    separate transactions so a cost-write failure can't leave the
    assistant row stuck at ``status="streaming"`` forever — which would
    surface to the user as a "thinking..." placeholder that never
    resolves. Message finalize is the hard requirement; the cost write
    is best-effort observability.
    """
    duration_ms = (time.perf_counter() - started_at) * _MS_PER_SECOND_FOR_LOG
    final_status = "failed" if aggregator.error_text else "complete"
    snapshot = aggregator.to_persisted_shape(status=final_status)
    try:
        async with _turn_session(turn_input) as session:
            await finalize_assistant_message(
                session,
                message_id=assistant_message_id,
                **snapshot,
            )
            await session.commit()
    except sa_exc.SQLAlchemyError:
        # Broad ``SQLAlchemyError`` (not bare ``Exception``) covers the full
        # set of SQLAlchemy failure modes that can reach this finalize path:
        # ``OperationalError``/``IntegrityError`` (the original narrow set)
        # plus ``PendingRollbackError`` / ``InvalidRequestError`` /
        # ``DataError`` raised when a prior statement inside the session
        # left the transaction in an unrecoverable state. Narrowing to just
        # the original two let those leak out of ``_finalize_turn`` (called
        # from ``run_turn``'s ``finally``) into the ``StreamingResponse``
        # generator after the body had already yielded, truncating the SSE
        # stream and stranding the assistant row at ``status="streaming"``.
        logger.exception(
            "%s_PERSIST_ERR conversation_id=%s message_id=%s",
            turn_input.log_tag,
            turn_input.conversation_id,
            assistant_message_id,
        )

    # Cost ledger write runs in its own transaction so a ledger-side
    # failure can't roll back the assistant-row finalize above. Runs for
    # every surface (web + Telegram) so the per-user cap applies uniformly.
    channel_message = turn_input.channel_message
    cost_model_id = (channel_message.get("model_id") or "") if channel_message else ""
    cost_surface = (channel_message.get("surface") or "") if channel_message else ""
    try:
        async with _turn_session(turn_input) as session:
            await record_turn_cost_if_enabled(
                session=session,
                aggregator=aggregator,
                user_id=turn_input.user_id,
                conversation_id=turn_input.conversation_id,
                model_id=cost_model_id,
                surface=cost_surface,
                log_tag=turn_input.log_tag,
            )
            await session.commit()
    except sa_exc.SQLAlchemyError:
        # See the matching except above: narrow ``OperationalError`` /
        # ``IntegrityError`` skips ``PendingRollbackError`` and friends,
        # which would propagate into the streaming generator and break
        # the SSE response after the body has yielded.
        logger.exception(
            "%s_COST_PERSIST_ERR conversation_id=%s message_id=%s",
            turn_input.log_tag,
            turn_input.conversation_id,
            assistant_message_id,
        )

    extras = " ".join(f"{key}={value}" for key, value in turn_input.log_extras.items())
    breakdown = (
        " ".join(f"{name}={count}" for name, count in sorted(event_breakdown.items())) or "none"
    )
    ttft_field = f"{ttft_ms:.1f}" if ttft_ms is not None else _TTFT_LOG_MISSING
    logger.info(
        "%s_OUT conversation_id=%s events=%d duration_ms=%.1f ttft_ms=%s "
        "input_tokens=%d output_tokens=%d breakdown=[%s] %s",
        turn_input.log_tag,
        turn_input.conversation_id,
        event_count,
        duration_ms,
        ttft_field,
        aggregator.total_input_tokens,
        aggregator.total_output_tokens,
        breakdown,
        extras,
    )
    # PR 10: announce completion (success / failure both surface here
    # because the caller wraps run_turn in a try/finally).  Subscribers
    # can react to spend, latency, etc.
    surface = (
        (turn_input.channel_message.get("surface") or "") if turn_input.channel_message else ""
    )
    model_id = (
        (turn_input.channel_message.get("model_id") or "") if turn_input.channel_message else ""
    )
    await publish_if_available(
        TurnCompletedEvent(
            user_id=turn_input.user_id,
            conversation_id=turn_input.conversation_id,
            surface=surface,
            model_id=model_id,
            status=final_status,
            duration_ms=duration_ms,
            ttft_ms=ttft_ms,
            input_tokens=aggregator.total_input_tokens,
            output_tokens=aggregator.total_output_tokens,
            cost_usd=aggregator.total_cost_usd,
            source=turn_input.log_tag.lower(),
        )
    )
    # Fire-and-forget LCM leaf compaction.  Runs after the assistant row is
    # finalized so the just-completed turn is eligible for compaction.
    # The helper handles the ``settings.lcm_enabled`` gate, task-strong-ref
    # bookkeeping, and exception suppression in one place.
    schedule_lcm_compaction(
        conversation_id=turn_input.conversation_id,
        user_id=turn_input.user_id,
        model_id=model_id,
    )
