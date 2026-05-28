"""Issue #254 - semantic retrieval + RRF blending tests.

Covers ``app.core.lcm.embeddings``:

- Deterministic hash embedder is stable across runs and gives
  paraphrases similar (non-zero, > 0) cosine.
- ``upsert_embedding`` skips empty content (acceptance criterion:
  empty assistant placeholders are not embedded).
- Content-hash skip path: re-embedding unchanged content does not
  rewrite the row.
- ``semantic_search`` returns ranked hits scoped to one conversation
  with no cross-conversation leak.
- ``reciprocal_rank_fusion`` blends lexical + semantic with explainable
  component ranks/scores.
- ``lcm_hybrid_search`` respects mode: lexical-only returns
  ``lexical_rank`` populated and ``semantic_rank`` None; semantic-only
  inverts it; hybrid surfaces both.
- Eval harness mode comparison: a paraphrased query that lexical
  alone misses is recoverable under hybrid retrieval on a seeded
  scenario.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm.embeddings import (
    EMBEDDING_DIM,
    DeterministicHashEmbedder,
    SemanticHit,
    content_hash,
    cosine_similarity,
    lcm_hybrid_search,
    reciprocal_rank_fusion,
    semantic_search,
    upsert_embedding,
)
from app.core.lcm.evals import (
    LCMEvalMode,
    run_eval,
    seed_embeddings_for_conversation,
    seed_scenario,
)
from app.core.tools.lcm_search import LCMSearchResult
from app.infrastructure.database.legacy import User
from app.models import (
    ChatMessage,
    Conversation,
    LCMEmbedding,
    LCMSummary,
)
from tests.evals.scenarios import all_scenarios


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    """Insert a fresh conversation owned by ``user``."""
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        title="embeddings test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def _make_message(
    session: AsyncSession,
    user: User,
    conv: Conversation,
    *,
    content: str,
    ordinal: int = 0,
    role: str = "user",
) -> ChatMessage:
    """Insert one raw chat message at ``ordinal``."""
    msg = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        user_id=user.id,
        ordinal=ordinal,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(msg)
    await session.flush()
    return msg


def test_deterministic_embedder_is_stable_across_runs() -> None:
    e = DeterministicHashEmbedder()
    text = "workspace-connect was dropped from onboarding"
    a = e.embed(text)
    b = e.embed(text)
    assert a == b
    assert len(a) == EMBEDDING_DIM


def test_deterministic_embedder_similar_text_has_positive_similarity() -> None:
    e = DeterministicHashEmbedder()
    a = e.embed("workspace-connect was dropped from onboarding")
    b = e.embed("we removed workspace-connect from the onboarding flow")
    c = e.embed("entirely unrelated text about pricing and tiers")

    sim_close = cosine_similarity(a, b)
    sim_far = cosine_similarity(a, c)
    assert sim_close > 0
    assert sim_close > sim_far


def test_content_hash_is_stable() -> None:
    assert content_hash("hello world") == content_hash("hello world")
    assert content_hash("hello world") != content_hash("hello world!")


@pytest.mark.anyio
async def test_upsert_embedding_skips_empty_content(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    msg = await _make_message(db_session, test_user, conv, content="")
    await db_session.commit()
    row = await upsert_embedding(
        db_session,
        conversation_id=conv.id,
        item_kind="message",
        item_id=msg.id,
        content="",
    )
    assert row is None


@pytest.mark.anyio
async def test_upsert_embedding_skips_when_content_hash_unchanged(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    msg = await _make_message(db_session, test_user, conv, content="hash skip path", ordinal=0)
    await db_session.commit()

    first = await upsert_embedding(
        db_session,
        conversation_id=conv.id,
        item_kind="message",
        item_id=msg.id,
        content="hash skip path",
    )
    assert first is not None
    first_created = first.created_at
    first_hash = first.content_hash

    second = await upsert_embedding(
        db_session,
        conversation_id=conv.id,
        item_kind="message",
        item_id=msg.id,
        content="hash skip path",
    )
    assert second is not None
    assert second.id == first.id
    assert second.created_at == first_created
    assert second.content_hash == first_hash


@pytest.mark.anyio
async def test_upsert_embedding_refreshes_when_content_changes(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    msg = await _make_message(db_session, test_user, conv, content="first content")
    await db_session.commit()

    first = await upsert_embedding(
        db_session,
        conversation_id=conv.id,
        item_kind="message",
        item_id=msg.id,
        content="first content",
    )
    assert first is not None
    first_hash = first.content_hash

    second = await upsert_embedding(
        db_session,
        conversation_id=conv.id,
        item_kind="message",
        item_id=msg.id,
        content="second content - different now",
    )
    assert second is not None
    assert second.id == first.id
    assert second.content_hash != first_hash


@pytest.mark.anyio
async def test_semantic_search_returns_ranked_hits(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    target = await _make_message(
        db_session,
        test_user,
        conv,
        content="we removed workspace-connect from onboarding to demo faster",
        ordinal=0,
    )
    decoy = await _make_message(
        db_session,
        test_user,
        conv,
        content="pricing tiers and active workspace caps for enterprise",
        ordinal=1,
    )
    await db_session.commit()

    for msg in (target, decoy):
        await upsert_embedding(
            db_session,
            conversation_id=conv.id,
            item_kind="message",
            item_id=msg.id,
            content=msg.content or "",
        )
    await db_session.commit()

    hits = await semantic_search(
        db_session,
        conversation_id=conv.id,
        query="dropped workspace-connect from the demo flow",
        limit=5,
    )
    assert hits
    assert hits[0].item_id == str(target.id)
    assert all(hit.score > 0 for hit in hits)


@pytest.mark.anyio
async def test_semantic_search_isolates_conversations(
    db_session: AsyncSession, test_user: User
) -> None:
    conv_a = await _make_conversation(db_session, test_user)
    conv_b = await _make_conversation(db_session, test_user)
    target = await _make_message(
        db_session, test_user, conv_b, content="leak target text", ordinal=0
    )
    await db_session.commit()
    await upsert_embedding(
        db_session,
        conversation_id=conv_b.id,
        item_kind="message",
        item_id=target.id,
        content=target.content or "",
    )
    await db_session.commit()

    hits = await semantic_search(db_session, conversation_id=conv_a.id, query="leak target text")
    assert hits == []


def test_reciprocal_rank_fusion_blends_components() -> None:
    lex: list[LCMSearchResult] = [
        {
            "item_kind": "message",
            "item_id": "m1",
            "ordinal": 0,
            "role": "user",
            "summary_depth": None,
            "summary_kind": None,
            "score": 0.5,
            "excerpt": "lex hit",
            "source_ids": ["m1"],
        },
        {
            "item_kind": "summary",
            "item_id": "s1",
            "ordinal": None,
            "role": None,
            "summary_depth": 0,
            "summary_kind": "normal",
            "score": 0.4,
            "excerpt": "summary hit",
            "source_ids": ["s1"],
        },
    ]
    sem: list[SemanticHit] = [
        SemanticHit(item_kind="summary", item_id="s1", score=0.9, excerpt="summary", metadata={}),
        SemanticHit(item_kind="message", item_id="m2", score=0.7, excerpt="m2", metadata={}),
    ]
    blended = reciprocal_rank_fusion(lexical=lex, semantic=sem)
    by_id = {item["item_id"]: item for item in blended}

    # s1 appears in both - higher final_score than m1 (lex only) or m2 (sem only).
    assert by_id["s1"]["lexical_rank"] == 2
    assert by_id["s1"]["semantic_rank"] == 1
    assert by_id["s1"]["final_score"] > by_id["m1"]["final_score"]
    assert by_id["s1"]["final_score"] > by_id["m2"]["final_score"]
    # Items hit by only one leg keep the other component null.
    assert by_id["m1"]["semantic_rank"] is None
    assert by_id["m2"]["lexical_rank"] is None


@pytest.mark.anyio
async def test_hybrid_search_modes_select_component_legs(
    db_session: AsyncSession, test_user: User
) -> None:
    conv = await _make_conversation(db_session, test_user)
    msg = await _make_message(
        db_session, test_user, conv, content="workspace-connect onboarding flow"
    )
    await db_session.commit()
    await upsert_embedding(
        db_session,
        conversation_id=conv.id,
        item_kind="message",
        item_id=msg.id,
        content=msg.content or "",
    )
    await db_session.commit()

    lex_only = await lcm_hybrid_search(
        db_session,
        conversation_id=conv.id,
        query="workspace-connect onboarding",
        mode="lexical",
    )
    sem_only = await lcm_hybrid_search(
        db_session,
        conversation_id=conv.id,
        query="workspace-connect onboarding",
        mode="semantic",
    )
    hybrid = await lcm_hybrid_search(
        db_session,
        conversation_id=conv.id,
        query="workspace-connect onboarding",
        mode="hybrid",
    )

    assert lex_only and lex_only[0]["semantic_rank"] is None
    assert sem_only and sem_only[0]["lexical_rank"] is None
    assert hybrid
    # Hybrid result for this single-item conversation should have
    # both legs populated.
    assert hybrid[0]["lexical_rank"] is not None
    assert hybrid[0]["semantic_rank"] is not None


@pytest.mark.anyio
async def test_seed_embeddings_writes_one_row_per_item(
    db_session: AsyncSession, test_user: User
) -> None:
    scenario = next(s for s in all_scenarios() if s.id == "pinpoint_summary_model")
    conv = await seed_scenario(db_session, user_id=test_user.id, scenario=scenario)
    await db_session.commit()

    count = await seed_embeddings_for_conversation(db_session, conversation_id=conv.id)
    await db_session.commit()
    stored = (
        (
            await db_session.execute(
                select(LCMEmbedding).where(LCMEmbedding.conversation_id == conv.id)
            )
        )
        .scalars()
        .all()
    )

    msg_count = len(
        (
            await db_session.execute(
                select(ChatMessage).where(ChatMessage.conversation_id == conv.id)
            )
        )
        .scalars()
        .all()
    )
    summary_count = len(
        (await db_session.execute(select(LCMSummary).where(LCMSummary.conversation_id == conv.id)))
        .scalars()
        .all()
    )
    assert count == msg_count + summary_count
    assert len(stored) == msg_count + summary_count


@pytest.mark.anyio
async def test_hybrid_mode_recovers_pinpoint_fact_via_eval_harness(
    db_session: AsyncSession, test_user: User
) -> None:
    """Hybrid retrieval surfaces the pinpoint fact a paraphrased query would miss lexically."""
    scenario = next(s for s in all_scenarios() if s.id == "pinpoint_summary_model")
    conv = await seed_scenario(db_session, user_id=test_user.id, scenario=scenario)
    await seed_embeddings_for_conversation(db_session, conversation_id=conv.id)
    await db_session.commit()

    result = await run_eval(
        db_session,
        conversation_id=conv.id,
        scenario=scenario,
        mode=LCMEvalMode.LCM_HYBRID,
        fresh_tail_count=4,
    )
    assert result.fact_pass is True
    assert {"lcm_search", "semantic_search"}.issubset(set(result.tools_called))
