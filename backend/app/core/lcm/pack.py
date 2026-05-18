"""LCM context packing - turn ranked candidates into a budgeted packet (issue #255).

Retrieval is half the problem.  Once ``lcm_search`` (or any other
candidate source) returns a ranked set of plausible items, the agent
still needs to decide *what to put in the model context*.  This
module is the packer: it takes structured candidates and produces a
token-bounded :class:`LCMPackedContext` along with explanation of
why each candidate was kept or dropped.

Design goals
------------
* **Deterministic.**  Same candidates + same budget produce the same
  packet, every run, so evals and diagnostics are reproducible.
* **Inspectable.**  Every kept item carries a ``packed_reason``;
  every rejected item carries a ``rejected_reason``.  The whole
  point of pruning is to make it auditable.
* **Composable.**  The packer is a pure function over candidates,
  not a database call.  Callers (``lcm_search``, future hybrid
  retrieval, eval harness, ``lcm_expand_query``) shape candidates
  however they want and let the packer apply the budget.

The rules (deliberately small + explainable):

1. Sort candidates by final score descending, with a kind-aware
   bias (``prefer_kind``) so callers can request raw-message-first
   or summary-first packing without re-scoring.
2. Drop summaries that are entirely subsumed by already-kept raw
   sources (``source_ids`` covered).  Symmetrically, drop raw
   messages whose only contribution is also in a kept summary's
   sources - except when the user signalled exact-fact preference.
3. Enforce the token budget; over-budget items are rejected with
   ``budget_exceeded`` rather than silently truncated.
4. Re-order kept items chronologically (ordinal ascending, with
   summaries floated to the top of their bucket so condensed
   history precedes raw turns).

The packer never silently changes assembly behaviour - it returns
a packet.  Routing the packet into a chat turn is a separate
decision (callers may compare unpruned candidates vs packed context
in evals before promoting the packer into the default path).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from typing import Any, Literal, TypedDict

# Reasons surfaced on kept / rejected items.  Kept as module
# constants so callers can switch on them programmatically without
# string-fishing.
REASON_TOP_SCORE = "top_score"
REASON_EXACT_FACT_PREFERENCE = "preferred_for_exact_fact"
REASON_BROAD_SUMMARY_PREFERENCE = "preferred_for_broad_query"
REASON_BUDGET_EXCEEDED = "budget_exceeded"
REASON_DUPLICATE_SOURCE_CHAIN = "source_chain_duplicate"
REASON_LOWER_RANKED_OVERLAP = "lower_ranked_overlap"

# Default token budget if the caller does not supply one.  Matches
# the ``lcm_leaf_chunk_tokens`` default in ``app.core.config`` so a
# typical leaf-summary's worth of context is the unit of packing.
_DEFAULT_TOKEN_BUDGET = 4_000

# Hard maximum on the number of kept items, regardless of budget.
# Prevents pathological inputs (1000 tiny excerpts) from packing
# into a single mega-context.
_MAX_KEPT_ITEMS = 32

# Multiplier applied to a candidate's effective score when the
# caller asks for a kind-biased pack.  Small enough that a strong
# score for the disfavoured kind still wins, large enough to break
# near-ties in favour of the requested kind.
_KIND_BIAS = 1.15

# When the query looks like an exact-fact lookup (model IDs, file
# paths, commands, error text), raw messages get a stronger lift
# because a raw turn contains the source phrasing while a summary
# would paraphrase.  This is independent of ``prefer_kind`` so the
# auto path still has guardrails.
_EXACT_FACT_RAW_BONUS = 1.25

# Fraction of a summary's source items that must already be in the
# kept set before we drop the summary as redundant.  The packer
# treats a summary as "covered" when more than half of its raw
# sources are already in the packet - any lower and the summary
# might still add cohesive prose the raw turns lack.
_SUMMARY_OVERLAP_DROP_THRESHOLD = 0.5

# Regex hints for "this is an exact-fact-style query".  Conservative
# - false positives would mis-prefer raw turns over summaries, which
# is the *less* harmful failure mode for an inspectable packer.
_EXACT_FACT_PATTERNS = (
    re.compile(r"\b(?:exact|exactly|filename|model id|command)\b", re.IGNORECASE),
    re.compile(r"\b\w+\.[a-zA-Z]{2,4}\b"),  # e.g. ``foo.py``, ``bar.md``
    re.compile(r"\b[a-z]+-[a-z0-9]+(?:-[a-z0-9]+)+\b"),  # kebab IDs / model names
    re.compile(r"\b(?:error|exception|stack trace)\b", re.IGNORECASE),
)


PackingHint = Literal["fresh_tail", "summary_first", "source_first", "timeline"]
PreferKind = Literal["auto", "messages", "summaries"]
ItemKind = Literal["message", "summary"]


class PackCandidate(TypedDict, total=False):
    """One retrieval candidate handed to the packer.

    Only ``item_kind``, ``item_id``, ``content``, and ``token_count``
    are required - the rest are optional metadata used for ordering
    and dedup.
    """

    item_kind: ItemKind
    item_id: str
    conversation_id: str
    ordinal: int | None
    role: str | None
    summary_depth: int | None
    summary_kind: str | None
    source_ids: list[str]
    lexical_score: float | None
    semantic_score: float | None
    final_score: float | None
    excerpt: str
    content: str
    token_count: int


class LCMPackedContextItem(TypedDict):
    """One item that survived packing."""

    item_kind: ItemKind
    item_id: str
    content: str
    token_count: int
    source_ids: list[str]
    packed_reason: str
    score: float
    ordinal: int | None
    summary_depth: int | None


class LCMPackingRejectedItem(TypedDict):
    """One item the packer dropped, with the reason."""

    item_kind: ItemKind
    item_id: str
    token_count: int
    rejected_reason: str
    score: float


class LCMPackedContext(TypedDict):
    """Full packing result - kept items + rejected items + diagnostics."""

    query: str
    token_budget: int
    token_count: int
    kept: list[LCMPackedContextItem]
    rejected: list[LCMPackingRejectedItem]
    diagnostics: dict[str, Any]


def _candidate_score(candidate: PackCandidate) -> float:
    """Pick the best available score from a candidate.

    Resolution order: ``final_score`` (set by hybrid blending) >
    ``lexical_score`` (set by :func:`lcm_search`) > ``semantic_score``
    (set by future semantic retrieval) > ``0.0``.
    """
    final = candidate.get("final_score")
    if final is not None:
        return float(final)
    lex = candidate.get("lexical_score")
    if lex is not None:
        return float(lex)
    sem = candidate.get("semantic_score")
    if sem is not None:
        return float(sem)
    return 0.0


def _effective_score(
    candidate: PackCandidate,
    *,
    prefer_kind: PreferKind,
    exact_fact: bool,
) -> float:
    """Apply kind-bias + exact-fact bonus to the raw candidate score."""
    base = _candidate_score(candidate)
    kind = candidate.get("item_kind")
    if (prefer_kind == "messages" and kind == "message") or (
        prefer_kind == "summaries" and kind == "summary"
    ):
        base *= _KIND_BIAS
    if exact_fact and kind == "message":
        base *= _EXACT_FACT_RAW_BONUS
    return base


def _looks_like_exact_fact_query(query: str) -> bool:
    """Heuristic: does the query look like an exact-fact lookup?"""
    if not query:
        return False
    return any(pattern.search(query) for pattern in _EXACT_FACT_PATTERNS)


def _approx_tokens(text: str) -> int:
    """Same 4-chars-per-token approximation used across LCM."""
    return max(1, math.ceil(len(text or "") / 4))


def _candidate_tokens(candidate: PackCandidate) -> int:
    """Resolve a candidate's token cost, preferring the supplied count."""
    raw = candidate.get("token_count")
    if isinstance(raw, int) and raw > 0:
        return raw
    return _approx_tokens(candidate.get("content") or candidate.get("excerpt") or "")


def _ordinal_for_sort(candidate: PackCandidate) -> int:
    """Chronological sort key.  Summaries float to the top of their bucket.

    Summaries get an even slot (``ordinal * 2``); raw messages get the
    odd slot (``ordinal * 2 + 1``) so when both share the same ordinal
    the summary always sorts first.  This is the behaviour the
    surrounding docstring describes; without the kind offset both kinds
    landed on the same key and the documented ordering never fired
    (Greptile P2 review).
    """
    ordinal = candidate.get("ordinal")
    if ordinal is not None:
        kind_offset = 0 if candidate.get("item_kind") == "summary" else 1
        return int(ordinal) * 2 + kind_offset
    # Summaries without explicit ordinal sort to the very front.
    return -1


def _initial_reason(
    candidate: PackCandidate,
    *,
    prefer_kind: PreferKind,
    exact_fact: bool,
) -> str:
    """Pick the keep-reason that applies to a candidate before dedup."""
    kind = candidate.get("item_kind")
    if exact_fact and kind == "message":
        return REASON_EXACT_FACT_PREFERENCE
    if prefer_kind == "summaries" and kind == "summary":
        return REASON_BROAD_SUMMARY_PREFERENCE
    if prefer_kind == "messages" and kind == "message":
        return REASON_EXACT_FACT_PREFERENCE
    return REASON_TOP_SCORE


def _is_subsumed_by_kept_summary(
    candidate: PackCandidate,
    kept_summary_source_ids: set[str],
) -> bool:
    """Is this raw message already covered by a kept summary's sources?"""
    if candidate.get("item_kind") != "message":
        return False
    return candidate.get("item_id", "") in kept_summary_source_ids


def _summary_overlap_ratio(candidate: PackCandidate, kept_message_ids: set[str]) -> float:
    """Fraction of a summary's sources already kept as raw messages."""
    if candidate.get("item_kind") != "summary":
        return 0.0
    sources = candidate.get("source_ids") or []
    if not sources:
        return 0.0
    overlap = sum(1 for sid in sources if sid in kept_message_ids)
    return overlap / len(sources)


class _PackState:
    """Mutable accumulator used by :func:`pack_context`.

    Defined ahead of the helper that consumes it so the helper can
    reference the type without a forward-string annotation.
    """

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.token_count = 0
        self.kept: list[LCMPackedContextItem] = []
        self.rejected: list[LCMPackingRejectedItem] = []
        self.kept_summary_source_ids: set[str] = set()
        self.kept_message_ids: set[str] = set()
        self.reject_counts: dict[str, int] = {}

    def would_overflow(self, tokens: int) -> bool:
        return (self.token_count + tokens) > self.budget

    def keep(
        self,
        candidate: PackCandidate,
        *,
        reason: str,
        score: float,
        tokens: int,
    ) -> None:
        """Record a kept candidate and update bookkeeping sets."""
        item_id = candidate.get("item_id", "")
        item_kind = candidate.get("item_kind")
        if item_kind not in ("message", "summary"):
            return
        content = candidate.get("content") or candidate.get("excerpt") or ""
        source_ids = list(candidate.get("source_ids") or [])
        self.kept.append(
            LCMPackedContextItem(
                item_kind=item_kind,
                item_id=item_id,
                content=content,
                token_count=tokens,
                source_ids=source_ids,
                packed_reason=reason,
                score=round(score, 6),
                ordinal=candidate.get("ordinal"),
                summary_depth=candidate.get("summary_depth"),
            )
        )
        self.token_count += tokens
        if item_kind == "summary":
            self.kept_summary_source_ids.update(source_ids)
        else:
            self.kept_message_ids.add(item_id)

    def reject(self, candidate: PackCandidate, reason: str, score: float) -> None:
        item_kind = candidate.get("item_kind")
        if item_kind not in ("message", "summary"):
            return
        tokens = _candidate_tokens(candidate)
        self.rejected.append(
            LCMPackingRejectedItem(
                item_kind=item_kind,
                item_id=candidate.get("item_id", ""),
                token_count=tokens,
                rejected_reason=reason,
                score=round(score, 6),
            )
        )
        self.reject_counts[reason] = self.reject_counts.get(reason, 0) + 1


def _try_pack_candidate(
    candidate: PackCandidate,
    *,
    state: _PackState,
    prefer_kind: PreferKind,
    exact_fact: bool,
) -> None:
    """Decide whether to keep, reject, or skip one candidate.

    Mutates ``state`` in place.  Keeps :func:`pack_context` flat
    enough to fit the project's 3-level nesting budget.
    """
    kind = candidate.get("item_kind")
    if kind not in ("message", "summary"):
        return

    score = _effective_score(candidate, prefer_kind=prefer_kind, exact_fact=exact_fact)
    tokens = _candidate_tokens(candidate)

    if _is_subsumed_by_kept_summary(candidate, state.kept_summary_source_ids):
        state.reject(candidate, REASON_DUPLICATE_SOURCE_CHAIN, score)
        return

    if (
        not exact_fact
        and _summary_overlap_ratio(candidate, state.kept_message_ids)
        > _SUMMARY_OVERLAP_DROP_THRESHOLD
    ):
        # We already have most of this summary's raw sources in the
        # packet; the summary now adds little.
        state.reject(candidate, REASON_LOWER_RANKED_OVERLAP, score)
        return

    if state.would_overflow(tokens):
        state.reject(candidate, REASON_BUDGET_EXCEEDED, score)
        return
    if len(state.kept) >= _MAX_KEPT_ITEMS:
        state.reject(candidate, REASON_BUDGET_EXCEEDED, score)
        return

    reason = _initial_reason(candidate, prefer_kind=prefer_kind, exact_fact=exact_fact)
    state.keep(candidate, reason=reason, score=score, tokens=tokens)


def pack_context(
    candidates: Iterable[PackCandidate],
    *,
    query: str = "",
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
    prefer_kind: PreferKind = "auto",
    chronological: bool = True,
) -> LCMPackedContext:
    """Pack ranked candidates into a token-bounded :class:`LCMPackedContext`.

    Args:
        candidates: Ranked-or-not candidate iterable.  The packer
            re-orders by effective score before walking.
        query: The user's question; used for the exact-fact heuristic
            and surfaced in diagnostics.
        token_budget: Hard token cap on the final packet.
        prefer_kind: ``"auto"`` (default) defers to score; ``"messages"``
            and ``"summaries"`` apply a small bias to break near-ties.
        chronological: When True (default) the kept list is re-sorted
            chronologically before return; otherwise it stays in
            score order.  Useful for consumers that want score-first
            ranking (e.g. the eval harness's diagnostic output).

    Returns:
        :class:`LCMPackedContext` with ``kept``, ``rejected``, and
        ``diagnostics``.
    """
    ordered = _order_candidates_for_packing(list(candidates), query=query, prefer_kind=prefer_kind)
    exact_fact = _looks_like_exact_fact_query(query)
    state = _PackState(budget=max(0, int(token_budget)))

    for candidate in ordered:
        _try_pack_candidate(
            candidate,
            state=state,
            prefer_kind=prefer_kind,
            exact_fact=exact_fact,
        )

    if chronological:
        state.kept.sort(
            key=lambda item: (
                item.get("ordinal") if item.get("ordinal") is not None else -1,
                item.get("summary_depth") or 0,
            )
        )

    diagnostics = _build_diagnostics(state, ordered, exact_fact)
    return LCMPackedContext(
        query=query,
        token_budget=state.budget,
        token_count=state.token_count,
        kept=state.kept,
        rejected=state.rejected,
        diagnostics=diagnostics,
    )


def _order_candidates_for_packing(
    candidates: list[PackCandidate],
    *,
    query: str,
    prefer_kind: PreferKind,
) -> list[PackCandidate]:
    """Sort candidates by effective score descending; stable for diagnostics."""
    exact_fact = _looks_like_exact_fact_query(query)
    return sorted(
        candidates,
        key=lambda c: (
            -_effective_score(c, prefer_kind=prefer_kind, exact_fact=exact_fact),
            _ordinal_for_sort(c),
        ),
    )


def _build_diagnostics(
    state: _PackState,
    ordered: Sequence[PackCandidate],
    exact_fact: bool,
) -> dict[str, Any]:
    """Materialise the diagnostics payload required by issue #255."""
    return {
        "candidates_considered": len(ordered),
        "kept_count": len(state.kept),
        "rejected_count": len(state.rejected),
        "rejection_breakdown": dict(state.reject_counts),
        "exact_fact_query": exact_fact,
        "final_order": [item["item_id"] for item in state.kept],
    }
