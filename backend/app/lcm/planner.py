"""LCM query planner - classify recall intent before retrieval (issue #256).

The retrieval stack now has lexical, semantic, hybrid, and packed
modes.  What it does *not* have is a planning layer that can tell a
"what exact model did we pick?" question apart from a "what did we
change our mind about?" question - and pick the right tool, subqueries,
and packing hint up front.

This module is that planning layer.  It accepts a user question (and
optional context such as prior assistant turns) and returns a
structured :class:`LCMQueryPlan` describing:

* intent classification (``exact_fact`` / ``source_lookup`` /
  ``broad_timeline`` / ``decision_trace`` / ``multi_hop`` /
  ``contradiction_check`` / ``unknown_or_unanswerable``),
* normalised question text,
* bounded subquery list (so broad plans cannot fan out unbounded),
* recommended retrieval modes,
* time + entity hints extracted from the question,
* packing hint surfacing the right item kind to prefer,
* citation requirement.

The default planner is **heuristic**: simple keyword rules picked to
cover the categories with high precision on a small fixture set.  A
model-based planner can plug in behind the same API in a future
iteration without changing the call sites.  The whole point of
issue #256 is that this layer is *inspectable* - keeping the
heuristic version deterministic preserves that.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.tools.lcm_search import LCM_STOPWORDS

Intent = Literal[
    "exact_fact",
    "source_lookup",
    "broad_timeline",
    "decision_trace",
    "multi_hop",
    "contradiction_check",
    "unknown_or_unanswerable",
]

RetrievalMode = Literal[
    "grep",
    "lexical",
    "semantic",
    "hybrid",
    "summary_walk",
]

PackingHint = Literal[
    "fresh_tail",
    "summary_first",
    "source_first",
    "timeline",
]

CitationRequirement = Literal["none", "preferred", "required"]


class LCMQueryPlan(BaseModel):
    """Structured plan for one user recall query.

    Mirrors the shape proposed in issue #256 so the agent loop, eval
    harness, and observability panel can all consume the same
    Pydantic type.
    """

    intent: Intent
    normalized_question: str
    subqueries: list[str] = Field(default_factory=list)
    retrieval_modes: list[RetrievalMode] = Field(default_factory=list)
    time_hints: list[str] = Field(default_factory=list)
    entity_hints: list[str] = Field(default_factory=list)
    packing_hint: PackingHint = "summary_first"
    citation_requirement: CitationRequirement = "preferred"
    max_budget_tokens: int | None = None
    diagnostics: dict[str, object] = Field(default_factory=dict)


# Subquery cap - hard ceiling so broad-query plans cannot fan out
# into unbounded retrieval calls (one of the explicit acceptance
# criteria in issue #256).
_MAX_SUBQUERIES = 4

# Default token budget hint surfaced on every plan.  Matches the
# packer's default so plan-aware code paths receive a value that
# pack_context can use without falling back.
_DEFAULT_BUDGET_TOKENS = 4_000

# Cue phrases used by the intent classifier.  Keeping them as module
# constants makes the heuristic auditable; tuning a single rule
# means editing one tuple, not chasing branches.
_INTENT_CUES: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    # Contradictions / change of mind - check first so a query that
    # also says "decision" still routes to contradiction_check.
    (
        "contradiction_check",
        (
            "change our mind",
            "changed our mind",
            "contradict",
            "still true",
            "rule out",
            "did we ever rule",
            "was it ever true",
            "did we reverse",
        ),
    ),
    # Multi-hop - "earlier X caused later Y" shape.  Checked before
    # decision_trace because the question superficially matches
    # "caused" but its real shape is multi-hop reasoning.
    (
        "multi_hop",
        (
            "earlier decision",
            "what caused later",
            "which earlier",
            "which decision caused",
            "follow from",
        ),
    ),
    # Decision trace - explanatory queries about reversals or causes.
    (
        "decision_trace",
        (
            "why did",
            "what caused",
            "what led to",
            "ended up",
            "decision",
            "decided",
        ),
    ),
    # Source / citation lookup.
    (
        "source_lookup",
        (
            "where did",
            "where does",
            "source",
            "citation",
            "cite",
            "evidence for",
        ),
    ),
    # Broad timeline.
    (
        "broad_timeline",
        (
            "last week",
            "this week",
            "this month",
            "last month",
            "yesterday",
            "today",
            "earlier",
            "when did",
            "timeline",
            "history",
        ),
    ),
    # Exact-fact cues are the catch-all for pinpoint phrasing.
    (
        "exact_fact",
        (
            "what exact",
            "exact",
            "exactly",
            "model id",
            "filename",
            "command",
            "error",
            "stack trace",
        ),
    ),
)

# Per-intent retrieval-mode recipes.  ``hybrid`` is the default
# leg for broad/multi-hop intents; ``grep`` + ``lexical`` cover
# pinpoint asks; ``summary_walk`` is reserved for decision-trace
# style questions that need to walk every leaf summary.
_INTENT_MODES: dict[Intent, list[RetrievalMode]] = {
    "exact_fact": ["grep", "lexical"],
    "source_lookup": ["lexical", "hybrid"],
    "broad_timeline": ["summary_walk", "hybrid"],
    "decision_trace": ["summary_walk", "hybrid"],
    "multi_hop": ["hybrid", "summary_walk"],
    "contradiction_check": ["hybrid", "summary_walk"],
    "unknown_or_unanswerable": ["lexical"],
}

_INTENT_PACKING: dict[Intent, PackingHint] = {
    "exact_fact": "source_first",
    "source_lookup": "source_first",
    "broad_timeline": "timeline",
    "decision_trace": "summary_first",
    "multi_hop": "summary_first",
    "contradiction_check": "summary_first",
    "unknown_or_unanswerable": "fresh_tail",
}

_INTENT_CITATION: dict[Intent, CitationRequirement] = {
    "exact_fact": "preferred",
    "source_lookup": "required",
    "broad_timeline": "preferred",
    "decision_trace": "required",
    "multi_hop": "required",
    "contradiction_check": "preferred",
    "unknown_or_unanswerable": "none",
}

_TIME_HINT_PATTERNS = (
    "today",
    "yesterday",
    "this week",
    "last week",
    "this month",
    "last month",
    "earlier",
    "later",
    "before",
    "after",
)

# Reuse the retrieval-stack stopword set so the planner tokenises
# identically to ``lcm_search`` and the eval harness.  Diverging
# lists caused inconsistent extraction between layers (Greptile P2
# review).
_STOPWORDS = LCM_STOPWORDS


def _normalise(text: str) -> str:
    """Trim + collapse whitespace + drop trailing punctuation."""
    body = " ".join((text or "").split()).strip()
    return body.rstrip("?.,!")


def _classify_intent(question: str) -> Intent:
    """Walk the cue table and pick the first matching intent."""
    lowered = question.lower()
    for intent, cues in _INTENT_CUES:
        if any(cue in lowered for cue in cues):
            return intent
    return "exact_fact"


def _extract_time_hints(question: str) -> list[str]:
    """Pull any of the recognised relative time phrases out of the question."""
    lowered = question.lower()
    return [phrase for phrase in _TIME_HINT_PATTERNS if phrase in lowered]


def _extract_entity_hints(question: str) -> list[str]:
    """Pull capitalised tokens + hyphenated identifiers as entity-style hints."""
    pascal = re.findall(r"\b[A-Z][a-zA-Z0-9]+\b", question)
    hyphenated = re.findall(r"\b[a-z]+(?:-[a-z0-9]+)+\b", question)
    seen: set[str] = set()
    out: list[str] = []
    for hint in (*pascal, *hyphenated):
        if hint.lower() in _STOPWORDS:
            continue
        if hint not in seen:
            seen.add(hint)
            out.append(hint)
    return out


def _split_subqueries(question: str, intent: Intent) -> list[str]:
    """Bounded subquery list for the planner output.

    For pinpoint intents we keep the question as-is so retrieval
    hits the exact phrase.  Broad / decision-trace intents split on
    conjunctions so the agent can fan out to bounded sub-questions.
    """
    base = _normalise(question)
    if not base:
        return []
    if intent in ("exact_fact", "source_lookup"):
        return [base][:_MAX_SUBQUERIES]
    parts = [p.strip() for p in re.split(r"\s+(?:and|or)\s+|;|,|/", base) if p.strip()]
    if not parts:
        return [base][:_MAX_SUBQUERIES]
    return parts[:_MAX_SUBQUERIES]


def _looks_unanswerable(question: str, intent: Intent) -> bool:
    """Catch obvious "we never discussed this" framings."""
    lowered = question.lower()
    refusal_cues = (
        "did we ever discuss",
        "did we mention",
        "was there ever",
        "anything about",
    )
    if intent == "contradiction_check":
        return False
    return any(cue in lowered for cue in refusal_cues)


def plan_query(question: str, *, context: str | None = None) -> LCMQueryPlan:
    """Classify the user's recall query and return a structured plan.

    Args:
        question: The user's raw question.
        context: Optional adjacent context (recent assistant prose,
            current draft, etc.).  Surfaced in diagnostics; future
            iterations may use it for entity hint enrichment.

    Returns:
        A populated :class:`LCMQueryPlan`.
    """
    normalised = _normalise(question)
    intent = _classify_intent(question)
    if _looks_unanswerable(question, intent):
        intent = "unknown_or_unanswerable"
    subqueries = _split_subqueries(question, intent)
    time_hints = _extract_time_hints(question)
    entity_hints = _extract_entity_hints(question)
    diagnostics: dict[str, object] = {
        "raw_question_length": len(question or ""),
        "context_provided": context is not None,
        "subqueries_capped_at": _MAX_SUBQUERIES,
    }
    return LCMQueryPlan(
        intent=intent,
        normalized_question=normalised,
        subqueries=subqueries,
        retrieval_modes=list(_INTENT_MODES.get(intent, ["lexical"])),
        time_hints=time_hints,
        entity_hints=entity_hints,
        packing_hint=_INTENT_PACKING.get(intent, "summary_first"),
        citation_requirement=_INTENT_CITATION.get(intent, "preferred"),
        max_budget_tokens=_DEFAULT_BUDGET_TOKENS,
        diagnostics=diagnostics,
    )
