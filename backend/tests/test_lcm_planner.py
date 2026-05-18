"""Issue #256 - LCM query planner tests.

Covers ``app.core.lcm.planner.plan_query``.

Behaviour we pin down:

- Each supported intent has at least one representative phrasing in
  the test suite (acceptance criterion: planner distinguishes the
  five primary intents listed in #256).
- ``unknown_or_unanswerable`` is reached for "did we ever discuss X"
  style questions.
- Subquery list is bounded by the documented cap (broad plans
  cannot fan out into unbounded retrieval loops).
- Retrieval modes and packing hint are intent-appropriate (exact
  fact → grep/lexical + source_first; broad timeline → summary_walk
  + timeline; decision trace → required citations).
- Time + entity hints are extracted from typical phrasings.
- The plan returns a JSON-serialisable Pydantic model so it can be
  surfaced in the issue-#251 observability panel.
"""

from __future__ import annotations

from app.core.lcm.planner import LCMQueryPlan, plan_query


def test_plan_exact_fact_intent_for_pinpoint_question() -> None:
    plan = plan_query("What exact model did we decide to use for summaries?")
    assert plan.intent == "exact_fact"
    assert plan.packing_hint == "source_first"
    assert "grep" in plan.retrieval_modes
    assert "lexical" in plan.retrieval_modes


def test_plan_source_lookup_intent_for_citation_question() -> None:
    plan = plan_query("Where did the 25-workspace pricing breakpoint claim come from?")
    assert plan.intent == "source_lookup"
    assert plan.citation_requirement == "required"
    assert plan.packing_hint == "source_first"


def test_plan_broad_timeline_intent_for_window_question() -> None:
    plan = plan_query("What did we decide last week about the demo flow?")
    assert plan.intent in ("broad_timeline", "decision_trace")
    assert plan.time_hints  # at least "last week" surfaces
    assert "summary_walk" in plan.retrieval_modes


def test_plan_decision_trace_intent_for_why_question() -> None:
    plan = plan_query("Why did we end up disabling auto-archive by default?")
    assert plan.intent in ("decision_trace", "broad_timeline")
    assert plan.citation_requirement == "required"


def test_plan_multi_hop_intent_for_causal_chain() -> None:
    plan = plan_query("Which earlier decision caused the missing-default-workspace bug?")
    assert plan.intent == "multi_hop"
    assert "hybrid" in plan.retrieval_modes
    assert plan.packing_hint == "summary_first"


def test_plan_contradiction_check_intent() -> None:
    plan = plan_query("What did we change our mind about regarding inbox archiving?")
    assert plan.intent == "contradiction_check"


def test_plan_unanswerable_intent_for_negative_recall() -> None:
    plan = plan_query("Did we ever discuss migrating our DNS provider?")
    assert plan.intent == "unknown_or_unanswerable"
    assert plan.retrieval_modes == ["lexical"]
    assert plan.citation_requirement == "none"


def test_plan_subqueries_bounded() -> None:
    plan = plan_query(
        "Last week we discussed pricing and onboarding and SSO and analytics and "
        "deploys and notifications and inbox archiving and theme switching"
    )
    assert len(plan.subqueries) <= 4


def test_plan_extracts_entity_hints_from_pascal_and_hyphenated_tokens() -> None:
    plan = plan_query("Earlier we removed workspace-connect from the Telegram demo")
    assert "Telegram" in plan.entity_hints
    assert any(h.startswith("workspace-connect") for h in plan.entity_hints)


def test_plan_returns_pydantic_model_serialisable() -> None:
    plan = plan_query("What exact model did we pick?")
    assert isinstance(plan, LCMQueryPlan)
    # Pydantic v2 dump should produce a plain dict.
    payload = plan.model_dump()
    assert payload["intent"] == "exact_fact"
    assert "subqueries" in payload
    assert "diagnostics" in payload


def test_plan_diagnostics_track_subquery_cap() -> None:
    plan = plan_query("What did we decide about pricing and onboarding?")
    assert plan.diagnostics["subqueries_capped_at"] == 4
