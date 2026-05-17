"""LCM retrieval eval harness — scoreboard for long-conversation recall.

Issue #252 asks: "judge LCM by data, not vibes".  This module is the
scoreboard.  It seeds deterministic long-conversation fixtures, runs
a candidate retrieval mode (baseline tail, LCM-assembled context,
``lcm_grep``, ``lcm_expand_query``, future ``lcm_search`` /
semantic / hybrid), and records pass/fail + cost/latency metrics.

The harness is **deterministic by default** so it can run in CI
without live LLM keys:

* "Answers" are produced by a small, transparent answerer
  (:func:`deterministic_answer`) that simply walks the retrieved
  context and quotes the spans that match the scenario's expected
  fact patterns.  This is intentionally weak — strong enough to tell
  whether the retrieval path surfaced the right text, no stronger.
  Real LLM scoring can sit behind a `LCM_EVAL_LIVE=1` env flag in a
  future iteration without changing the public shape here.

* Seeded conversations write into the same SQLAlchemy tables the
  production code uses (``chat_messages`` / ``lcm_summaries`` /
  ``lcm_context_items``) so retrieval/assembly hits the real code
  path, not a parallel fake.

Public API
----------
``LCMEvalScenario``     - dataclass describing one eval case.
``LCMEvalMode``         - which retrieval mode is under test.
``LCMEvalResult``       - outcome + metrics for a (scenario, mode) run.
``seed_scenario``       - bulk-insert a scenario's turns + summaries.
``run_eval``            - run one (scenario, mode) and return the result.
``run_eval_matrix``     - run every scenario x mode pair.
``deterministic_answer``- CI-safe answerer used by every mode by default.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm import assemble_context
from app.core.lcm.embeddings import (
    DeterministicHashEmbedder,
    Embedder,
    lcm_hybrid_search,
    upsert_embedding,
)
from app.core.lcm.pack import PackCandidate, pack_context
from app.core.tools.lcm_grep import lcm_grep
from app.core.tools.lcm_search import LCM_STOPWORDS, lcm_search
from app.core.tools.lcm_search import format_results as format_search_results
from app.models import (
    ChatMessage,
    Conversation,
    LCMContextItem,
    LCMSummary,
    LCMSummarySource,
)

# Same 4-chars-per-token approximation used everywhere else in LCM.
_CHARS_PER_TOKEN = 4

# Hard cap on retrieved-context characters surfaced to the answerer.
# Keeps CI runtime stable when a scenario seeds a huge transcript.
_MAX_CONTEXT_CHARS = 64_000

# Default lcm_grep result cap when the mode-specific runner does not
# pass one through.  Matches the production tool's default so the
# harness measures realistic behaviour.
_GREP_RESULT_CAP = 10

# Phrases the deterministic answerer uses when no expected fact is
# present in the retrieved context — distinct strings so eval output
# is greppable and unambiguous.
_ANSWER_NO_EVIDENCE = "[no evidence in retrieved context]"
_ANSWER_NEGATIVE = "[history does not contain this]"

ScenarioIntent = Literal[
    "pinpoint",
    "broad",
    "multi_hop",
    "contradiction",
    "source",
    "negative",
]


class LCMEvalMode(StrEnum):
    """Retrieval modes the harness can compare.

    Future modes (``lcm_search`` lexical/semantic/hybrid) will be
    appended here as the corresponding issues land.  The value of the
    enum is what shows up in :class:`LCMEvalResult.mode`, so add new
    members rather than renaming existing ones once the harness is
    persisted in any rollout report.
    """

    BASELINE = "baseline"
    LCM_ASSEMBLED = "lcm_assembled"
    LCM_GREP = "lcm_grep"
    LCM_SEARCH = "lcm_search"
    LCM_SEARCH_PACKED = "lcm_search_packed"
    LCM_SEMANTIC = "lcm_semantic"
    LCM_HYBRID = "lcm_hybrid"


@dataclass(frozen=True)
class SeedSummary:
    """One pre-compacted summary inserted in place of raw turns.

    Attributes:
        content: The summary prose to store in ``lcm_summaries.content``.
        replaces_turn_indexes: Indexes into the scenario's
            ``seed_turns`` whose context items will be replaced by
            this summary's single context item.  Indexes must be
            contiguous; the summary takes the lowest replaced
            ordinal, mirroring the in-place rewrite in
            :func:`app.core.lcm.compact_leaf_if_needed`.
        depth: ``0`` for leaf summaries, ``1+`` for condensed.
        kind: ``"normal"`` / ``"aggressive"`` / ``"fallback"``.
    """

    content: str
    replaces_turn_indexes: list[int]
    depth: int = 0
    kind: str = "normal"


@dataclass(frozen=True)
class LCMEvalScenario:
    """One eval case - seeded conversation + question + expected facts.

    Attributes:
        id: Stable identifier used in result reporting (snake-case).
        intent: Which scenario *type* this case represents.  Mirrors
            issue #252's six required categories.
        question: The user's question for this turn.
        seed_turns: ``[{"role", "content"}]`` list inserted as
            ``ChatMessage`` rows in order.  Every entry becomes a
            ``LCMContextItem`` so the assembly path sees them.
        seed_summaries: Optional pre-compacted summaries to insert in
            place of the oldest turns; useful for scenarios where the
            target fact lives in a summary rather than a raw turn.
            Each entry replaces the raw context items at the indexes
            in ``replaces_turn_indexes`` with a single summary item.
        expected_fact_patterns: Regexes (case-insensitive) that must
            appear in the deterministic answer for ``fact_pass`` to
            be True.  For negative scenarios this list is empty.
        expected_source_substrings: Strings that must appear in the
            retrieved context for ``source_pass`` to be True.  Empty
            list means no source check (e.g. negative scenarios).
        expects_unanswerable: When True the scenario is in the
            "should refuse to answer" category - passing means the
            answerer emits :data:`_ANSWER_NEGATIVE` and ``fact_pass``
            tracks that decision, not pattern hits.
        notes: Free-text rationale shown next to results.
    """

    id: str
    intent: ScenarioIntent
    question: str
    seed_turns: list[dict[str, str]]
    seed_summaries: list[SeedSummary] = field(default_factory=list)
    expected_fact_patterns: list[str] = field(default_factory=list)
    expected_source_substrings: list[str] = field(default_factory=list)
    expects_unanswerable: bool = False
    notes: str = ""


@dataclass
class LCMEvalResult:
    """Outcome + metrics for one (scenario, mode) run."""

    scenario_id: str
    mode: str
    question: str
    answer: str
    fact_pass: bool
    source_pass: bool
    context_chars: int
    context_tokens: int
    output_tokens: int
    latency_ms: float
    tools_called: list[str]
    notes: str = ""


def _approx_tokens(text: str) -> int:
    """Rough token estimate; mirrors :mod:`app.core.lcm.__init__`."""
    return max(0, len(text or "") // _CHARS_PER_TOKEN)


def _utcnow() -> datetime:
    """Timezone-aware UTC now."""
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
    now = _utcnow()
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
            created_at=_utcnow(),
            updated_at=_utcnow(),
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
            token_count=_approx_tokens(seed.content),
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


def _flatten_assembled(context: list[dict[str, object]]) -> str:
    """Concatenate an assembled-context list into a single text blob."""
    parts: list[str] = []
    for turn in context:
        role = str(turn.get("role") or "")
        content = str(turn.get("content") or "")
        if content:
            parts.append(f"{role.upper()}: {content}")
    blob = "\n\n".join(parts)
    return blob[:_MAX_CONTEXT_CHARS]


def deterministic_answer(
    question: str,
    retrieved_context: str,
    *,
    scenario: LCMEvalScenario,
) -> str:
    """Build a CI-safe "answer" by quoting matches from retrieved context.

    For positive scenarios the answerer scans ``retrieved_context`` for
    each ``expected_fact_patterns`` regex (case-insensitive).  Every
    match is quoted into the answer text exactly once; if no patterns
    hit, the answerer emits :data:`_ANSWER_NO_EVIDENCE`.

    For negative scenarios (``expects_unanswerable=True``) the answer
    is :data:`_ANSWER_NEGATIVE` whenever none of the optional
    "false-positive" patterns appear — modelling a well-behaved agent
    that refuses to invent facts.

    The point of this answerer is to make eval results reflect the
    retrieval/assembly layer, not a downstream LLM's prose style.
    """
    blob = retrieved_context or ""
    if scenario.expects_unanswerable:
        return _negative_answer(scenario, blob)

    quotes = _collect_pattern_quotes(scenario.expected_fact_patterns, blob)
    if not quotes:
        return _ANSWER_NO_EVIDENCE
    return " | ".join(quotes)


def _negative_answer(scenario: LCMEvalScenario, blob: str) -> str:
    """Return the answer for a negative-recall scenario.

    A "false positive" pattern is any regex listed in
    ``expected_fact_patterns`` — those phrases are the things the
    scenario asserts must *not* be invented.  When none of them
    appear in the retrieved context the agent should refuse, so the
    answerer emits :data:`_ANSWER_NEGATIVE`.  When any do appear, the
    answerer echoes them so ``fact_pass`` flips False and the
    failure is visible.
    """
    quotes = _collect_pattern_quotes(scenario.expected_fact_patterns, blob)
    if not quotes:
        return _ANSWER_NEGATIVE
    return " | ".join(quotes)


def _collect_pattern_quotes(patterns: Sequence[str], blob: str) -> list[str]:
    """Return one quote per pattern that matches inside ``blob``."""
    quotes: list[str] = []
    for raw in patterns:
        try:
            compiled = re.compile(raw, flags=re.IGNORECASE | re.DOTALL)
        except re.error:
            continue
        hit = compiled.search(blob)
        if hit is not None:
            quotes.append(hit.group(0).strip())
    return quotes


def _fact_pass(answer: str, scenario: LCMEvalScenario) -> bool:
    """Decide whether the answer satisfies the scenario's fact rule."""
    if scenario.expects_unanswerable:
        return answer == _ANSWER_NEGATIVE
    if not scenario.expected_fact_patterns:
        return True
    return all(
        re.search(pat, answer, flags=re.IGNORECASE | re.DOTALL) is not None
        for pat in scenario.expected_fact_patterns
    )


def _source_pass(retrieved_context: str, scenario: LCMEvalScenario) -> bool:
    """Decide whether the retrieved context contained every expected source span."""
    if not scenario.expected_source_substrings:
        return True
    blob_lower = (retrieved_context or "").lower()
    return all(snippet.lower() in blob_lower for snippet in scenario.expected_source_substrings)


async def _retrieve_baseline(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Baseline: the old ``LIMIT 20``-style raw-tail slice — no LCM machinery."""
    result = await session.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role.in_(["user", "assistant"]),
        )
        .order_by(ChatMessage.ordinal.desc())
        .limit(fresh_tail_count)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    blob = "\n\n".join(f"{m.role.upper()}: {m.content or ''}" for m in rows)
    return blob[:_MAX_CONTEXT_CHARS], []


async def _retrieve_lcm_assembled(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """LCM mode: protected fresh tail + every summary, via :func:`assemble_context`."""
    context = await assemble_context(
        session,
        conversation_id=conversation_id,
        fresh_tail_count=fresh_tail_count,
    )
    return _flatten_assembled(context), []


async def _retrieve_lcm_grep(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    question: str,
) -> tuple[str, list[str]]:
    """Grep-assisted recall: synthesise short queries, union the matches.

    Picks the longest few content words from ``question`` and runs them
    through :func:`lcm_grep`.  The deterministic answerer then quotes
    matching spans.  We do not stitch grep output into a chat call
    because the harness's answerer is intentionally retrieval-only.
    """
    queries = _extract_search_terms(question)
    blob_parts: list[str] = []
    for term in queries:
        snippet = await lcm_grep(
            session,
            conversation_id=conversation_id,
            query=term,
            limit=_GREP_RESULT_CAP,
        )
        blob_parts.append(snippet)
    blob = "\n\n".join(blob_parts)
    return blob[:_MAX_CONTEXT_CHARS], ["lcm_grep"]


async def _retrieve_lcm_search(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    question: str,
) -> tuple[str, list[str]]:
    """Ranked lexical retrieval via :func:`lcm_search`."""
    results = await lcm_search(
        session,
        conversation_id=conversation_id,
        query=question,
    )
    blob = format_search_results(question, results)
    return blob[:_MAX_CONTEXT_CHARS], ["lcm_search"]


async def _retrieve_hybrid(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    question: str,
    mode: str,
    embedder: Embedder | None = None,
) -> tuple[str, list[str]]:
    """Hybrid (or one-leg) retrieval via :func:`lcm_hybrid_search`."""
    used_embedder = embedder or DeterministicHashEmbedder()
    rows = await lcm_hybrid_search(
        session,
        conversation_id=conversation_id,
        query=question,
        mode=mode,  # type: ignore[arg-type]
        embedder=used_embedder,
    )
    parts = [
        f"[{row['item_kind'].upper()} score={row['final_score']:.3f}] {row['excerpt']}"
        for row in rows
    ]
    blob = "\n\n".join(parts)
    tools = (
        ["lcm_search", "semantic_search"]
        if mode == "hybrid"
        else (["lcm_search"] if mode == "lexical" else ["semantic_search"])
    )
    return blob[:_MAX_CONTEXT_CHARS], tools


async def _retrieve_lcm_search_packed(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    question: str,
) -> tuple[str, list[str]]:
    """Ranked search routed through the issue-#255 context packer."""
    raw_results = await lcm_search(
        session,
        conversation_id=conversation_id,
        query=question,
    )
    candidates: list[PackCandidate] = [
        PackCandidate(
            item_kind=row["item_kind"],
            item_id=row["item_id"],
            ordinal=row.get("ordinal"),
            role=row.get("role"),
            summary_depth=row.get("summary_depth"),
            summary_kind=row.get("summary_kind"),
            source_ids=list(row.get("source_ids") or []),
            lexical_score=row.get("score"),
            final_score=row.get("score"),
            excerpt=row.get("excerpt", ""),
            content=row.get("excerpt", ""),
            token_count=max(1, len(row.get("excerpt", "")) // _CHARS_PER_TOKEN),
        )
        for row in raw_results
    ]
    packed = pack_context(candidates, query=question)
    rendered_parts = [
        f"[{item['item_kind'].upper()} reason={item['packed_reason']}]\n{item['content']}"
        for item in packed["kept"]
    ]
    blob = "\n\n".join(rendered_parts)
    return blob[:_MAX_CONTEXT_CHARS], ["lcm_search", "pack_context"]


def _extract_search_terms(question: str) -> list[str]:
    """Pull a handful of content-bearing words out of a question.

    Uses the shared :data:`app.core.tools.lcm_search.LCM_STOPWORDS`
    set so the eval harness tokenises identically to the retrieval
    scorer it benchmarks.
    """
    raw_tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", question.lower())
    seen: set[str] = set()
    terms: list[str] = []
    for token in raw_tokens:
        if token in LCM_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms[:5]


_MODE_DISPATCH = {
    LCMEvalMode.BASELINE: ("baseline tail", []),
    LCMEvalMode.LCM_ASSEMBLED: ("assemble_context", []),
    LCMEvalMode.LCM_GREP: ("lcm_grep-assisted", ["lcm_grep"]),
}


async def run_eval(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    mode: LCMEvalMode,
    fresh_tail_count: int = 4,
) -> LCMEvalResult:
    """Run one (scenario, mode) pair and return the structured result.

    Retrieval failures for *known* modes never raise - the eval is a
    measurement, so a missing tool or empty context surfaces as
    ``fact_pass=False`` rather than a test exception.  An unknown
    ``mode`` (one absent from :data:`_MODE_RETRIEVERS`) raises
    ``ValueError`` so callers discover missing registrations
    immediately, rather than silently scoring against an empty
    context.
    """
    started = time.perf_counter()
    blob, tools_called = await _retrieve_for_mode(
        session,
        conversation_id=conversation_id,
        scenario=scenario,
        mode=mode,
        fresh_tail_count=fresh_tail_count,
    )
    answer = deterministic_answer(scenario.question, blob, scenario=scenario)
    latency_ms = (time.perf_counter() - started) * 1000.0

    return LCMEvalResult(
        scenario_id=scenario.id,
        mode=mode.value,
        question=scenario.question,
        answer=answer,
        fact_pass=_fact_pass(answer, scenario),
        source_pass=_source_pass(blob, scenario),
        context_chars=len(blob),
        context_tokens=_approx_tokens(blob),
        output_tokens=_approx_tokens(answer),
        latency_ms=latency_ms,
        tools_called=tools_called,
        notes=scenario.notes,
    )


async def _retrieve_for_mode(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    mode: LCMEvalMode,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Dispatch table for retrieval modes — keeps :func:`run_eval` flat.

    The function is intentionally a flat lookup over the supported
    modes; adding a new mode means appending another ``async def
    _retrieve_*`` and a single line in :data:`_MODE_RETRIEVERS`.
    """
    retriever = _MODE_RETRIEVERS.get(mode)
    if retriever is None:
        raise ValueError(f"unsupported eval mode: {mode!r}")
    return await retriever(
        session,
        conversation_id=conversation_id,
        scenario=scenario,
        fresh_tail_count=fresh_tail_count,
    )


async def _adapt_baseline(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Wrap the baseline retriever in the dispatch signature."""
    del scenario  # unused
    return await _retrieve_baseline(
        session,
        conversation_id=conversation_id,
        fresh_tail_count=fresh_tail_count,
    )


async def _adapt_lcm_assembled(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Wrap the LCM-assembled retriever in the dispatch signature."""
    del scenario
    return await _retrieve_lcm_assembled(
        session,
        conversation_id=conversation_id,
        fresh_tail_count=fresh_tail_count,
    )


async def _adapt_lcm_grep(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Wrap the lcm_grep retriever in the dispatch signature."""
    del fresh_tail_count
    return await _retrieve_lcm_grep(
        session,
        conversation_id=conversation_id,
        question=scenario.question,
    )


async def _adapt_lcm_search(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Wrap the ranked lcm_search retriever in the dispatch signature."""
    del fresh_tail_count
    return await _retrieve_lcm_search(
        session,
        conversation_id=conversation_id,
        question=scenario.question,
    )


async def _adapt_lcm_search_packed(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Wrap the packed-search retriever in the dispatch signature."""
    del fresh_tail_count
    return await _retrieve_lcm_search_packed(
        session,
        conversation_id=conversation_id,
        question=scenario.question,
    )


async def _adapt_semantic(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Wrap semantic-only hybrid_search in the dispatch signature."""
    del fresh_tail_count
    return await _retrieve_hybrid(
        session,
        conversation_id=conversation_id,
        question=scenario.question,
        mode="semantic",
    )


async def _adapt_hybrid(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Wrap full hybrid_search in the dispatch signature."""
    del fresh_tail_count
    return await _retrieve_hybrid(
        session,
        conversation_id=conversation_id,
        question=scenario.question,
        mode="hybrid",
    )


_MODE_RETRIEVERS = {
    LCMEvalMode.BASELINE: _adapt_baseline,
    LCMEvalMode.LCM_ASSEMBLED: _adapt_lcm_assembled,
    LCMEvalMode.LCM_GREP: _adapt_lcm_grep,
    LCMEvalMode.LCM_SEARCH: _adapt_lcm_search,
    LCMEvalMode.LCM_SEARCH_PACKED: _adapt_lcm_search_packed,
    LCMEvalMode.LCM_SEMANTIC: _adapt_semantic,
    LCMEvalMode.LCM_HYBRID: _adapt_hybrid,
}


async def run_eval_matrix(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    scenarios: Sequence[LCMEvalScenario],
    modes: Sequence[LCMEvalMode],
    fresh_tail_count: int = 4,
) -> list[LCMEvalResult]:
    """Seed every scenario and run every mode against each one.

    Returns a flat list of :class:`LCMEvalResult` in
    ``(scenario, mode)`` order so callers can pivot however they
    like.
    """
    results: list[LCMEvalResult] = []
    for scenario in scenarios:
        conv = await seed_scenario(session, user_id=user_id, scenario=scenario)
        for mode in modes:
            result = await run_eval(
                session,
                conversation_id=conv.id,
                scenario=scenario,
                mode=mode,
                fresh_tail_count=fresh_tail_count,
            )
            results.append(result)
    return results
