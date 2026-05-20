"""Seed scenario fixtures into the production ORM.

Writing through the real ``ChatMessage`` / ``LCMSummary`` /
``LCMContextItem`` / ``LCMSummarySource`` rows means retrieval/assembly
hits the same schema as production, not a parallel fake.  The seeding
helpers also embed every persisted row when callers want to exercise
semantic / hybrid retrieval (see
:func:`seed_embeddings_for_conversation`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm.embeddings import (
    DeterministicHashEmbedder,
    Embedder,
    upsert_embedding,
)
from app.core.lcm.evals.types import LCMEvalScenario
from app.models import (
    ChatMessage,
    Conversation,
    LCMContextItem,
    LCMSummary,
    LCMSummarySource,
)

# Same 4-chars-per-token approximation used everywhere else in LCM.
_CHARS_PER_TOKEN = 4


def approx_tokens(text: str) -> int:
    """Rough token estimate; mirrors :mod:`app.core.lcm.__init__`.

    Package-public so the runner can size :class:`LCMEvalResult` token
    counts without duplicating the constant.
    """
    return max(0, len(text or "") // _CHARS_PER_TOKEN)


def utcnow() -> datetime:
    """Timezone-aware UTC now used by every seeded row."""
    return datetime.now(UTC)


async def seed_embeddings_for_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    embedder: Embedder | None = None,
) -> int:
    """Embed every persisted message + summary for one conversation.

    Used by tests that want to exercise the semantic / hybrid
    retrieval paths after :func:`seed_scenario` has written raw
    rows.  Returns the number of embeddings written or refreshed
    so callers can assert on the count.
    """
    used_embedder = embedder or DeterministicHashEmbedder()
    count = 0
    msg_result = await session.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
    )
    for msg in msg_result.scalars().all():
        row = await upsert_embedding(
            session,
            conversation_id=conversation_id,
            item_kind="message",
            item_id=msg.id,
            content=msg.content or "",
            embedder=used_embedder,
        )
        if row is not None:
            count += 1
    sum_result = await session.execute(
        select(LCMSummary).where(LCMSummary.conversation_id == conversation_id)
    )
    for summary in sum_result.scalars().all():
        row = await upsert_embedding(
            session,
            conversation_id=conversation_id,
            item_kind="summary",
            item_id=summary.id,
            content=summary.content or "",
            embedder=used_embedder,
        )
        if row is not None:
            count += 1
    return count


async def seed_scenario(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    scenario: LCMEvalScenario,
    conversation_id: uuid.UUID | None = None,
) -> Conversation:
    """Insert one scenario's conversation, turns, and summaries.

    Writes through the production ORM so retrieval paths exercise the
    real schema.  Caller commits the session (this function only
    flushes) so the test harness can wrap multiple scenarios in
    one transaction when desired.

    Args:
        session: Open async session.
        user_id: Owning user UUID.
        scenario: Scenario fixture to seed.
        conversation_id: Optional pre-allocated UUID so the caller can
            assert on it without round-tripping.  A fresh UUID is
            generated when omitted.

    Returns:
        The persisted :class:`Conversation` row.
    """
    conv_id = conversation_id or uuid.uuid4()
    now = utcnow()
    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title=f"eval/{scenario.id}",
        created_at=now,
        updated_at=now,
    )
    session.add(conv)
    await session.flush()

    inserted_message_ids = await _seed_turns(session, conv=conv, user_id=user_id, scenario=scenario)
    await _seed_summaries(session, conv=conv, scenario=scenario, message_ids=inserted_message_ids)
    await session.flush()
    return conv


async def _seed_turns(
    session: AsyncSession,
    *,
    conv: Conversation,
    user_id: uuid.UUID,
    scenario: LCMEvalScenario,
) -> list[uuid.UUID]:
    """Insert every raw turn for a scenario.  Returns inserted IDs in order."""
    inserted: list[uuid.UUID] = []
    for ordinal, turn in enumerate(scenario.seed_turns):
        msg = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            user_id=user_id,
            ordinal=ordinal,
            role=turn["role"],
            content=turn["content"],
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(msg)
        await session.flush()
        inserted.append(msg.id)
        session.add(
            LCMContextItem(
                conversation_id=conv.id,
                ordinal=ordinal,
                item_kind="message",
                item_id=msg.id,
            )
        )
    return inserted


async def _seed_summaries(
    session: AsyncSession,
    *,
    conv: Conversation,
    scenario: LCMEvalScenario,
    message_ids: list[uuid.UUID],
) -> None:
    """Insert pre-compacted summaries, rewriting context items in place."""
    for seed in scenario.seed_summaries:
        summary = LCMSummary(
            conversation_id=conv.id,
            depth=seed.depth,
            content=seed.content,
            token_count=approx_tokens(seed.content),
            summary_kind=seed.kind,
        )
        session.add(summary)
        await session.flush()

        replaced_indexes = sorted(seed.replaces_turn_indexes)
        for src_ordinal, turn_index in enumerate(replaced_indexes):
            session.add(
                LCMSummarySource(
                    summary_id=summary.id,
                    source_kind="message",
                    source_id=message_ids[turn_index],
                    source_ordinal=src_ordinal,
                )
            )

        # Replace the context-item rows that previously pointed at the
        # raw turns with a single summary row at the lowest ordinal.
        slot_ordinal = replaced_indexes[0]
        ids_to_remove = [message_ids[i] for i in replaced_indexes if i < len(message_ids)]
        existing = await session.execute(
            select(LCMContextItem).where(
                LCMContextItem.conversation_id == conv.id,
                LCMContextItem.item_id.in_(ids_to_remove),
            )
        )
        for row in existing.scalars().all():
            await session.delete(row)
        await session.flush()
        session.add(
            LCMContextItem(
                conversation_id=conv.id,
                ordinal=slot_ordinal,
                item_kind="summary",
                item_id=summary.id,
            )
        )
