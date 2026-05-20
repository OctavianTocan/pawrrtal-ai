"""Dataclasses + enum + literal alias shared by the LCM eval package.

These types describe one eval *case* (:class:`LCMEvalScenario`) and the
shape of its outcome (:class:`LCMEvalResult`), plus the seeded summary
fixture (:class:`SeedSummary`) and the retrieval-mode enum
(:class:`LCMEvalMode`).  Pulling them into their own module lets the
seeding / answerer / retrievers / runner modules import only the data
they need without dragging in retrieval implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

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
            answerer emits :data:`app.core.lcm.evals.answerer.ANSWER_NEGATIVE`
            and ``fact_pass`` tracks that decision, not pattern hits.
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
