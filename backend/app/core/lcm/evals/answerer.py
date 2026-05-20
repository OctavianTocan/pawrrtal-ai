"""CI-safe deterministic answerer + pass/fail scoring helpers.

For positive scenarios the answerer scans the retrieved context for
each :attr:`LCMEvalScenario.expected_fact_patterns` regex and emits the
matches.  For negative scenarios (:attr:`LCMEvalScenario.expects_unanswerable`
True) it refuses with :data:`_ANSWER_NEGATIVE` whenever none of the
false-positive patterns appear.  The point is to make eval results
reflect retrieval/assembly, not a downstream LLM's prose style.

:func:`fact_pass` and :func:`source_pass` apply the scenario's pass
criteria to the emitted answer + retrieved context blob.  They're
public within the ``evals`` package so the runner can import them
without reaching across the privacy boundary.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.core.lcm.evals.types import LCMEvalScenario

# Phrases the deterministic answerer uses when no expected fact is
# present in the retrieved context — distinct strings so eval output
# is greppable and unambiguous.
_ANSWER_NO_EVIDENCE = "[no evidence in retrieved context]"
_ANSWER_NEGATIVE = "[history does not contain this]"


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


def fact_pass(answer: str, scenario: LCMEvalScenario) -> bool:
    """Decide whether the answer satisfies the scenario's fact rule."""
    if scenario.expects_unanswerable:
        return answer == _ANSWER_NEGATIVE
    if not scenario.expected_fact_patterns:
        return True
    return all(
        re.search(pat, answer, flags=re.IGNORECASE | re.DOTALL) is not None
        for pat in scenario.expected_fact_patterns
    )


def source_pass(retrieved_context: str, scenario: LCMEvalScenario) -> bool:
    """Decide whether the retrieved context contained every expected source span."""
    if not scenario.expected_source_substrings:
        return True
    blob_lower = (retrieved_context or "").lower()
    return all(snippet.lower() in blob_lower for snippet in scenario.expected_source_substrings)
