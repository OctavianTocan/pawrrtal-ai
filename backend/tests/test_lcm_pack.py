"""Issue #255 - LCM context packing tests.

Covers ``app.core.lcm.pack.pack_context``.

Behaviour we pin down:

- Empty candidates produce an empty packet with diagnostics zeroed.
- Budget overflow rejects oversized items with ``budget_exceeded``,
  not silent truncation.
- Duplicate source chains: a raw message subsumed by a kept summary
  is rejected with ``source_chain_duplicate``; symmetrically a
  summary whose sources are already in the kept set is rejected
  with ``lower_ranked_overlap`` when not in exact-fact mode.
- ``prefer_kind="summaries"`` floats summaries above near-tied
  raw messages.
- ``prefer_kind="messages"`` does the inverse, and the exact-fact
  heuristic auto-prefers raw messages when the query looks like a
  pinpoint lookup (filename, model id, error text).
- Kept items appear in chronological order by default.
- Every kept item carries a packed_reason; every rejected item
  carries a rejected_reason.  Diagnostics surface counts +
  rejection breakdown.
"""

from __future__ import annotations

from app.core.lcm.pack import (
    REASON_BROAD_SUMMARY_PREFERENCE,
    REASON_BUDGET_EXCEEDED,
    REASON_DUPLICATE_SOURCE_CHAIN,
    REASON_EXACT_FACT_PREFERENCE,
    REASON_LOWER_RANKED_OVERLAP,
    REASON_TOP_SCORE,
    PackCandidate,
    pack_context,
)


def _msg(
    *,
    item_id: str,
    content: str,
    ordinal: int,
    score: float,
    tokens: int | None = None,
) -> PackCandidate:
    return PackCandidate(
        item_kind="message",
        item_id=item_id,
        ordinal=ordinal,
        role="user",
        final_score=score,
        excerpt=content,
        content=content,
        token_count=tokens if tokens is not None else max(1, len(content) // 4),
        source_ids=[item_id],
    )


def _summary(
    *,
    item_id: str,
    content: str,
    score: float,
    source_ids: list[str] | None = None,
    tokens: int | None = None,
    depth: int = 0,
) -> PackCandidate:
    return PackCandidate(
        item_kind="summary",
        item_id=item_id,
        summary_depth=depth,
        summary_kind="normal",
        final_score=score,
        excerpt=content,
        content=content,
        token_count=tokens if tokens is not None else max(1, len(content) // 4),
        source_ids=list(source_ids or []),
    )


def test_pack_empty_candidates_returns_empty_packet() -> None:
    packed = pack_context([], query="anything", token_budget=1000)
    assert packed["kept"] == []
    assert packed["rejected"] == []
    assert packed["token_count"] == 0
    assert packed["diagnostics"]["candidates_considered"] == 0


def test_pack_respects_budget_and_rejects_overflow() -> None:
    a = _msg(item_id="m1", content="alpha " * 20, ordinal=0, score=0.9, tokens=40)
    b = _msg(item_id="m2", content="bravo " * 20, ordinal=1, score=0.8, tokens=40)
    c = _msg(item_id="m3", content="charlie " * 20, ordinal=2, score=0.7, tokens=40)

    packed = pack_context([a, b, c], query="alpha", token_budget=80)

    kept_ids = [item["item_id"] for item in packed["kept"]]
    rejected_ids = [item["item_id"] for item in packed["rejected"]]
    assert kept_ids == ["m1", "m2"]  # chronological
    assert rejected_ids == ["m3"]
    assert all(item["packed_reason"] for item in packed["kept"])
    assert packed["rejected"][0]["rejected_reason"] == REASON_BUDGET_EXCEEDED
    assert packed["token_count"] <= 80


def test_pack_drops_message_subsumed_by_kept_summary() -> None:
    summary = _summary(
        item_id="s1",
        content="summary covers m1 and m2",
        score=0.9,
        source_ids=["m1", "m2"],
        tokens=30,
    )
    msg_in = _msg(item_id="m1", content="raw m1", ordinal=0, score=0.5, tokens=10)
    msg_out = _msg(item_id="m_other", content="raw other", ordinal=2, score=0.8, tokens=10)

    packed = pack_context(
        [summary, msg_in, msg_out],
        token_budget=200,
        prefer_kind="summaries",
    )

    kept_ids = {item["item_id"] for item in packed["kept"]}
    rejected = {item["item_id"]: item for item in packed["rejected"]}
    assert "s1" in kept_ids
    assert "m_other" in kept_ids
    assert "m1" in rejected
    assert rejected["m1"]["rejected_reason"] == REASON_DUPLICATE_SOURCE_CHAIN


def test_pack_drops_summary_whose_sources_are_already_kept() -> None:
    msg_a = _msg(item_id="m1", content="raw m1 fact", ordinal=0, score=0.9, tokens=10)
    msg_b = _msg(item_id="m2", content="raw m2 fact", ordinal=1, score=0.85, tokens=10)
    summary = _summary(
        item_id="s1",
        content="summary of m1 and m2",
        score=0.6,
        source_ids=["m1", "m2"],
        tokens=30,
    )

    packed = pack_context(
        [msg_a, msg_b, summary],
        token_budget=200,
        prefer_kind="messages",
    )

    rejected = {item["item_id"]: item for item in packed["rejected"]}
    assert "s1" in rejected
    assert rejected["s1"]["rejected_reason"] == REASON_LOWER_RANKED_OVERLAP


def test_pack_summary_preference_floats_summaries_in_tie() -> None:
    msg = _msg(item_id="m1", content="raw discussion", ordinal=5, score=0.5, tokens=15)
    summary = _summary(item_id="s1", content="summary discussion", score=0.5, tokens=15)

    packed = pack_context(
        [msg, summary],
        query="broad question",
        token_budget=200,
        prefer_kind="summaries",
        chronological=False,
    )

    kept_ids = [item["item_id"] for item in packed["kept"]]
    assert kept_ids[0] == "s1"
    assert packed["kept"][0]["packed_reason"] == REASON_BROAD_SUMMARY_PREFERENCE


def test_pack_exact_fact_query_lifts_raw_messages() -> None:
    msg = _msg(
        item_id="m1",
        content="we picked gemini-2.5-flash-preview-05-20",
        ordinal=4,
        score=0.5,
        tokens=15,
    )
    summary = _summary(
        item_id="s1",
        content="model decision summary",
        score=0.5,
        tokens=15,
    )

    packed = pack_context(
        [summary, msg],
        query="exact model id we picked: gemini-2.5-flash-preview-05-20",
        token_budget=200,
        chronological=False,
    )

    kept_ids = [item["item_id"] for item in packed["kept"]]
    assert kept_ids[0] == "m1"
    assert packed["kept"][0]["packed_reason"] == REASON_EXACT_FACT_PREFERENCE
    assert packed["diagnostics"]["exact_fact_query"] is True


def test_pack_keeps_chronological_order_in_kept_list() -> None:
    msg0 = _msg(item_id="m0", content="oldest", ordinal=0, score=0.1, tokens=5)
    msg5 = _msg(item_id="m5", content="middle", ordinal=5, score=0.9, tokens=5)
    msg10 = _msg(item_id="m10", content="newest", ordinal=10, score=0.5, tokens=5)

    packed = pack_context([msg5, msg10, msg0], token_budget=200)

    ordinals = [item["ordinal"] for item in packed["kept"]]
    assert ordinals == [0, 5, 10]


def test_pack_every_kept_item_has_packed_reason() -> None:
    msgs = [
        _msg(item_id=f"m{i}", content=f"content {i}", ordinal=i, score=0.5, tokens=5)
        for i in range(4)
    ]
    packed = pack_context(msgs, token_budget=200)
    assert all(item["packed_reason"] for item in packed["kept"])
    assert all(item["score"] is not None for item in packed["kept"])
    assert {item["packed_reason"] for item in packed["kept"]} == {REASON_TOP_SCORE}


def test_pack_diagnostics_count_rejections_by_reason() -> None:
    big = _msg(item_id="big", content="x" * 4000, ordinal=0, score=0.9, tokens=1000)
    summary = _summary(
        item_id="s1",
        content="summary",
        score=0.8,
        source_ids=["m1"],
        tokens=10,
    )
    sub = _msg(item_id="m1", content="raw m1", ordinal=1, score=0.7, tokens=5)

    packed = pack_context([big, summary, sub], token_budget=50, prefer_kind="summaries")

    breakdown = packed["diagnostics"]["rejection_breakdown"]
    assert breakdown.get(REASON_BUDGET_EXCEEDED, 0) >= 1
    assert breakdown.get(REASON_DUPLICATE_SOURCE_CHAIN, 0) >= 1
    assert packed["diagnostics"]["kept_count"] == len(packed["kept"])
    assert packed["diagnostics"]["candidates_considered"] == 3
