"""LCM retrieval eval harness — scoreboard for long-conversation recall.

Issue #252 asks: "judge LCM by data, not vibes".  This package is the
scoreboard.  It seeds deterministic long-conversation fixtures, runs
a candidate retrieval mode (baseline tail, LCM-assembled context,
``lcm_grep``, ``lcm_search``, semantic, hybrid, packed search), and
records pass/fail + cost/latency metrics.

The harness is **deterministic by default** so it can run in CI
without live LLM keys:

* "Answers" are produced by a small, transparent answerer
  (:func:`deterministic_answer`) that simply walks the retrieved
  context and quotes the spans that match the scenario's expected
  fact patterns.  This is intentionally weak — strong enough to tell
  whether the retrieval path surfaced the right text, no stronger.
  Real LLM scoring can sit behind a ``LCM_EVAL_LIVE=1`` env flag in a
  future iteration without changing the public shape here.

* Seeded conversations write into the same SQLAlchemy tables the
  production code uses (``chat_messages`` / ``lcm_summaries`` /
  ``lcm_context_items``) so retrieval/assembly hits the real code
  path, not a parallel fake.

Module layout
-------------
* :mod:`.types` — dataclasses + enum + literal alias
  (:class:`LCMEvalScenario`, :class:`LCMEvalResult`, :class:`SeedSummary`,
  :class:`LCMEvalMode`, :data:`ScenarioIntent`).
* :mod:`.seeding` — :func:`seed_scenario` writes conversation + turns +
  summaries through the production ORM; :func:`seed_embeddings_for_conversation`
  embeds the rows for semantic/hybrid retrieval tests.
* :mod:`.answerer` — :func:`deterministic_answer` plus the
  ``fact_pass`` / ``source_pass`` scoring helpers.
* :mod:`.retrievers` — one ``retrieve_*`` coroutine per
  :class:`LCMEvalMode`.
* :mod:`.runner` — :func:`run_eval` (one scenario + mode) and
  :func:`run_eval_matrix` (every pair).

Public API
----------
``LCMEvalScenario``              - dataclass describing one eval case.
``LCMEvalMode``                  - which retrieval mode is under test.
``LCMEvalResult``                - outcome + metrics for a (scenario, mode) run.
``SeedSummary``                  - pre-compacted summary fixture.
``ScenarioIntent``               - literal alias for scenario categories.
``seed_scenario``                - bulk-insert a scenario's turns + summaries.
``seed_embeddings_for_conversation`` - embed persisted rows for hybrid tests.
``deterministic_answer``         - CI-safe answerer used by every mode by default.
``run_eval``                     - run one (scenario, mode) and return the result.
``run_eval_matrix``              - run every scenario x mode pair.
"""

from __future__ import annotations

from app.core.lcm.evals.answerer import deterministic_answer
from app.core.lcm.evals.runner import run_eval, run_eval_matrix
from app.core.lcm.evals.seeding import (
    seed_embeddings_for_conversation,
    seed_scenario,
)
from app.core.lcm.evals.types import (
    LCMEvalMode,
    LCMEvalResult,
    LCMEvalScenario,
    ScenarioIntent,
    SeedSummary,
)

__all__ = [
    "LCMEvalMode",
    "LCMEvalResult",
    "LCMEvalScenario",
    "ScenarioIntent",
    "SeedSummary",
    "deterministic_answer",
    "run_eval",
    "run_eval_matrix",
    "seed_embeddings_for_conversation",
    "seed_scenario",
]
