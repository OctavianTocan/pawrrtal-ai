"""End-to-end tests for the LCM retrieval eval harness (issue #252).

Drives :mod:`app.core.lcm.evals` over the seeded scenarios from
:mod:`tests.evals.scenarios` in baseline / LCM-assembled / LCM-grep
modes and asserts the harness reports the expected pass/fail
distribution.

These are *eval* tests rather than unit tests — they exercise the
real retrieval/assembly code path through the production ORM.  They
deliberately do not call any live LLM provider; the harness's
deterministic answerer makes the suite CI-safe.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm.evals import (
    LCMEvalMode,
    LCMEvalResult,
    run_eval,
    run_eval_matrix,
    seed_scenario,
)
from app.db import User
from tests.evals.scenarios import all_scenarios


def _result_for(
    results: list[LCMEvalResult],
    *,
    scenario_id: str,
    mode: LCMEvalMode,
) -> LCMEvalResult:
    """Pick one result out of a matrix run by ``(scenario, mode)``."""
    for item in results:
        if item.scenario_id == scenario_id and item.mode == mode.value:
            return item
    raise AssertionError(f"no result for {scenario_id} / {mode.value}")


@pytest.mark.anyio
async def test_at_least_six_scenarios_cover_required_intents() -> None:
    scenarios = all_scenarios()
    intents = {s.intent for s in scenarios}
    assert len(scenarios) >= 6
    assert intents == {
        "pinpoint",
        "broad",
        "multi_hop",
        "contradiction",
        "source",
        "negative",
    }


@pytest.mark.anyio
async def test_seed_scenario_persists_turns_and_summaries(
    db_session: AsyncSession, test_user: User
) -> None:
    scenario = next(s for s in all_scenarios() if s.id == "multi_hop_onboarding_regression")
    conv = await seed_scenario(db_session, user_id=test_user.id, scenario=scenario)
    await db_session.commit()

    from sqlalchemy import select

    from app.models import ChatMessage, LCMContextItem, LCMSummary

    message_count = (
        (
            await db_session.execute(
                select(ChatMessage).where(ChatMessage.conversation_id == conv.id)
            )
        )
        .scalars()
        .all()
    )
    summary_count = (
        (await db_session.execute(select(LCMSummary).where(LCMSummary.conversation_id == conv.id)))
        .scalars()
        .all()
    )
    item_count = (
        (
            await db_session.execute(
                select(LCMContextItem).where(LCMContextItem.conversation_id == conv.id)
            )
        )
        .scalars()
        .all()
    )

    assert len(message_count) == len(scenario.seed_turns)
    assert len(summary_count) == 1
    # One context item per turn, minus the 4 collapsed into the summary, plus
    # the one summary item itself.
    assert len(item_count) == len(scenario.seed_turns) - 4 + 1


@pytest.mark.anyio
async def test_baseline_misses_facts_outside_fresh_tail(
    db_session: AsyncSession, test_user: User
) -> None:
    """The whole point: baseline tail mode loses facts outside the recent window."""
    scenario = next(s for s in all_scenarios() if s.id == "pinpoint_summary_model")
    conv = await seed_scenario(db_session, user_id=test_user.id, scenario=scenario)
    await db_session.commit()

    result = await run_eval(
        db_session,
        conversation_id=conv.id,
        scenario=scenario,
        mode=LCMEvalMode.BASELINE,
        fresh_tail_count=4,
    )
    assert result.fact_pass is False
    assert result.source_pass is False
    assert result.context_tokens > 0


@pytest.mark.anyio
async def test_lcm_assembled_surfaces_summary_node(
    db_session: AsyncSession, test_user: User
) -> None:
    scenario = next(s for s in all_scenarios() if s.id == "multi_hop_onboarding_regression")
    conv = await seed_scenario(db_session, user_id=test_user.id, scenario=scenario)
    await db_session.commit()

    result = await run_eval(
        db_session,
        conversation_id=conv.id,
        scenario=scenario,
        mode=LCMEvalMode.LCM_ASSEMBLED,
        fresh_tail_count=4,
    )
    # The summary preserves the workspace-connect decision so the
    # multi-hop scenario is answerable under LCM_ASSEMBLED.
    assert result.fact_pass is True
    assert result.source_pass is True


@pytest.mark.anyio
async def test_lcm_grep_recovers_pinpoint_fact(db_session: AsyncSession, test_user: User) -> None:
    scenario = next(s for s in all_scenarios() if s.id == "pinpoint_summary_model")
    conv = await seed_scenario(db_session, user_id=test_user.id, scenario=scenario)
    await db_session.commit()

    result = await run_eval(
        db_session,
        conversation_id=conv.id,
        scenario=scenario,
        mode=LCMEvalMode.LCM_GREP,
        fresh_tail_count=4,
    )
    assert result.fact_pass is True
    assert "lcm_grep" in result.tools_called


@pytest.mark.anyio
async def test_negative_scenario_refuses_to_answer(
    db_session: AsyncSession, test_user: User
) -> None:
    scenario = next(s for s in all_scenarios() if s.id == "negative_recall_dns_migration")
    conv = await seed_scenario(db_session, user_id=test_user.id, scenario=scenario)
    await db_session.commit()

    result = await run_eval(
        db_session,
        conversation_id=conv.id,
        scenario=scenario,
        mode=LCMEvalMode.LCM_ASSEMBLED,
        fresh_tail_count=4,
    )
    assert result.fact_pass is True  # well-behaved refusal
    assert "history does not contain this" in result.answer


@pytest.mark.anyio
async def test_eval_matrix_runs_every_scenario_for_every_mode(
    db_session: AsyncSession, test_user: User
) -> None:
    scenarios = all_scenarios()
    modes = [
        LCMEvalMode.BASELINE,
        LCMEvalMode.LCM_ASSEMBLED,
        LCMEvalMode.LCM_GREP,
    ]
    results = await run_eval_matrix(
        db_session,
        user_id=test_user.id,
        scenarios=scenarios,
        modes=modes,
        fresh_tail_count=4,
    )
    await db_session.commit()

    assert len(results) == len(scenarios) * len(modes)
    assert {r.scenario_id for r in results} == {s.id for s in scenarios}
    assert {r.mode for r in results} == {m.value for m in modes}

    # The headline claim of issue #252 — LCM-assembled mode wins on
    # at least one scenario where baseline fails.  Concrete check:
    # pinpoint summary model is unanswerable from the tail alone but
    # answerable from any LCM-backed mode.
    baseline = _result_for(results, scenario_id="pinpoint_summary_model", mode=LCMEvalMode.BASELINE)
    grep = _result_for(results, scenario_id="pinpoint_summary_model", mode=LCMEvalMode.LCM_GREP)
    assert baseline.fact_pass is False
    assert grep.fact_pass is True


@pytest.mark.anyio
async def test_search_packed_mode_carries_pack_tool_in_trace(
    db_session: AsyncSession, test_user: User
) -> None:
    """LCM_SEARCH_PACKED routes lcm_search results through the issue-#255 packer."""
    scenario = next(s for s in all_scenarios() if s.id == "pinpoint_summary_model")
    conv = await seed_scenario(db_session, user_id=test_user.id, scenario=scenario)
    await db_session.commit()

    result = await run_eval(
        db_session,
        conversation_id=conv.id,
        scenario=scenario,
        mode=LCMEvalMode.LCM_SEARCH_PACKED,
        fresh_tail_count=4,
    )
    assert "lcm_search" in result.tools_called
    assert "pack_context" in result.tools_called
    assert result.fact_pass is True


@pytest.mark.anyio
async def test_result_records_cost_and_latency_fields(
    db_session: AsyncSession, test_user: User
) -> None:
    scenario = next(s for s in all_scenarios() if s.id == "source_recall_pricing_breakpoint")
    conv = await seed_scenario(db_session, user_id=test_user.id, scenario=scenario)
    await db_session.commit()

    result = await run_eval(
        db_session,
        conversation_id=conv.id,
        scenario=scenario,
        mode=LCMEvalMode.LCM_ASSEMBLED,
        fresh_tail_count=4,
    )

    assert result.context_tokens > 0
    assert result.context_chars > 0
    assert result.latency_ms >= 0.0
    assert result.output_tokens >= 0
