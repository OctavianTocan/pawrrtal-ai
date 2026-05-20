"""Top-level eval runner: dispatches retrievers, scores, returns results.

The runner glues the package together: it wraps each retriever in a
uniform dispatch signature, looks the mode up in
:data:`_MODE_RETRIEVERS`, calls the deterministic answerer, and
returns a structured :class:`LCMEvalResult`.  :func:`run_eval_matrix`
fan-outs every (scenario, mode) pair so callers can pivot the flat
result list however they like.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm.evals.answerer import (
    deterministic_answer,
    fact_pass,
    source_pass,
)
from app.core.lcm.evals.retrievers import (
    retrieve_baseline,
    retrieve_hybrid,
    retrieve_lcm_assembled,
    retrieve_lcm_grep,
    retrieve_lcm_search,
    retrieve_lcm_search_packed,
)
from app.core.lcm.evals.seeding import approx_tokens, seed_scenario
from app.core.lcm.evals.types import LCMEvalMode, LCMEvalResult, LCMEvalScenario

# A retriever wrapped in the uniform dispatch signature.  Every
# adapter accepts the same kwargs even when the underlying retriever
# ignores some of them; the runner picks whichever adapter the mode
# enum maps to.
_AdaptedRetriever = Callable[
    ...,
    Awaitable[tuple[str, list[str]]],
]


async def _adapt_baseline(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    scenario: LCMEvalScenario,
    fresh_tail_count: int,
) -> tuple[str, list[str]]:
    """Wrap the baseline retriever in the dispatch signature."""
    del scenario  # unused
    return await retrieve_baseline(
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
    return await retrieve_lcm_assembled(
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
    return await retrieve_lcm_grep(
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
    return await retrieve_lcm_search(
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
    return await retrieve_lcm_search_packed(
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
    return await retrieve_hybrid(
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
    return await retrieve_hybrid(
        session,
        conversation_id=conversation_id,
        question=scenario.question,
        mode="hybrid",
    )


_MODE_RETRIEVERS: dict[LCMEvalMode, _AdaptedRetriever] = {
    LCMEvalMode.BASELINE: _adapt_baseline,
    LCMEvalMode.LCM_ASSEMBLED: _adapt_lcm_assembled,
    LCMEvalMode.LCM_GREP: _adapt_lcm_grep,
    LCMEvalMode.LCM_SEARCH: _adapt_lcm_search,
    LCMEvalMode.LCM_SEARCH_PACKED: _adapt_lcm_search_packed,
    LCMEvalMode.LCM_SEMANTIC: _adapt_semantic,
    LCMEvalMode.LCM_HYBRID: _adapt_hybrid,
}


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
    retrieve_*`` (or wrapper here) and a single line in
    :data:`_MODE_RETRIEVERS`.
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
        fact_pass=fact_pass(answer, scenario),
        source_pass=source_pass(blob, scenario),
        context_chars=len(blob),
        context_tokens=approx_tokens(blob),
        output_tokens=approx_tokens(answer),
        latency_ms=latency_ms,
        tools_called=tools_called,
        notes=scenario.notes,
    )


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
