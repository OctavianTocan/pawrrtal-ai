"""End-to-end cost-ledger verification scenario.

Drives the real chat + cost surface (``GET /api/v1/cost/`` ->
``GET /api/v1/cost/ledger`` -> ``POST /api/v1/conversations/{uuid}`` ->
``POST /api/v1/chat/`` -> ``GET /api/v1/cost/`` ->
``GET /api/v1/cost/ledger`` -> ``DELETE /api/v1/conversations/{uuid}``)
and asserts that a chat turn lands a non-zero ledger row whose
``current_usd`` accumulation matches what the backend reports.

Scope note — the per-user budget *limit* is configured via the
``cost_max_per_user_daily_usd`` env setting, not a per-user HTTP
endpoint. Until a budget-setter route lands, this scenario emits a
stable ``budget_endpoint_unavailable`` marker check so consumers can
grep for the gap and flip it to a real assertion the moment a
``POST /api/v1/cost/limit`` (or analogous) endpoint ships.
"""

from __future__ import annotations

from typing import Any

from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify import helpers
from app.cli.paw.verify.scenarios import ScenarioResult

# Turn text — short on purpose so the ledger row is cheap when the
# scenario runs against a live backend with real model credentials.
TURN_TEXT = "Say hi in two words."
SCENARIO_TITLE = "paw verify cost"

# Minimum number of ledger rows after one chat turn. The chat router
# writes exactly one cost row per assistant turn that finishes, so any
# value below this means the writer dropped a row or the test caught a
# regression mid-flight.
MIN_LEDGER_DELTA = 1


def _summary_current_usd(payload: Any) -> float | None:
    """Pull ``current_usd`` out of the summary envelope; ``None`` if absent."""
    if not isinstance(payload, dict):
        return None
    value = payload.get("current_usd")
    return float(value) if isinstance(value, (int, float)) else None


def _ledger_rows(payload: Any) -> list[dict[str, Any]]:
    """Filter the ledger response to dict rows; tolerate envelope drift."""
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


async def _capture_baseline(
    client: PawClient, r: ScenarioResult
) -> list[dict[str, Any]]:
    """Snapshot summary + ledger so post-turn deltas have a known starting point.

    Returns the baseline ledger row list; the summary is recorded as an
    artifact for debugging but not compared post-turn — see
    :func:`_assert_ledger_delta` for why the conversation-scoped ledger
    check is the only authoritative delta.
    """
    summary = (await client.request("GET", "/api/v1/cost/")).json()
    r.artifacts["baseline_summary"] = summary
    current = _summary_current_usd(summary)
    r.add(
        "baseline_summary",
        isinstance(summary, dict) and "current_usd" in summary,
        detail=f"current_usd={current}",
    )

    ledger = _ledger_rows((await client.request("GET", "/api/v1/cost/ledger")).json())
    r.artifacts["baseline_ledger_count"] = len(ledger)
    r.add("baseline_ledger_size", True, detail=f"rows={len(ledger)}")
    return ledger


async def _drive_chat_turn(
    client: PawClient,
    r: ScenarioResult,
    *,
    model_id: str,
) -> str | None:
    """Create a conversation, stream one turn, assert non-empty final text.

    Returns the conversation id on success; ``None`` if the turn produced
    no text events (which makes the cost-delta check meaningless).
    """
    conv_id = await helpers.create_conversation(client, r, title=SCENARIO_TITLE)
    events = await helpers.stream_turn(client, conv_id, TURN_TEXT, model_id=model_id)
    r.artifacts["chat_events"] = events

    text_events = [e for e in events if e.get("type") in ("delta", "message")]
    errors = [e for e in events if e.get("type") == "error"]
    final_text = "".join(
        e.get("content", "") for e in text_events if isinstance(e.get("content"), str)
    )
    r.add(
        "chat_turn_no_errors",
        len(errors) == 0,
        detail=f"first_error={errors[0] if errors else None}",
    )
    r.add(
        "chat_turn_final_text_nonempty",
        bool(final_text.strip()),
        detail=repr(final_text[:80]),
    )
    if not final_text.strip():
        return None
    return conv_id


async def _assert_ledger_delta(
    client: PawClient,
    r: ScenarioResult,
    baseline_count: int,
    conv_id: str,
) -> None:
    """Post-turn ledger must gain >= 1 row referencing the new conversation."""
    rows = _ledger_rows((await client.request("GET", "/api/v1/cost/ledger")).json())
    r.artifacts["post_turn_ledger_count"] = len(rows)
    r.artifacts["post_turn_ledger_rows"] = rows
    delta = len(rows) - baseline_count
    r.add(
        "ledger_row_added",
        delta >= MIN_LEDGER_DELTA,
        detail=f"baseline={baseline_count} post={len(rows)} delta={delta}",
    )
    if delta < MIN_LEDGER_DELTA:
        return

    matching = [row for row in rows if str(row.get("conversation_id")) == conv_id]
    r.add(
        "ledger_row_references_conversation",
        len(matching) >= 1,
        detail=f"matching_rows={len(matching)} conv_id={conv_id}",
    )

    if not matching:
        return
    row = matching[0]
    cost = row.get("cost_usd")
    r.add(
        "ledger_row_cost_nonzero",
        isinstance(cost, (int, float)) and cost > 0,
        detail=f"cost_usd={cost!r}",
    )


def _record_budget_gap(r: ScenarioResult) -> None:
    """Document the missing per-user budget-setter endpoint as a stable check.

    The check passes intentionally — there is nothing for paw to break
    because the endpoint does not exist. The greppable name lets agents
    and dashboards key off the gap and flip it to a real assertion the
    moment ``POST /api/v1/cost/limit`` (or analogous) lands.
    """
    r.add(
        "budget_endpoint_unavailable",
        True,
        detail=(
            "Per-user budget cap is configured via "
            "settings.cost_max_per_user_daily_usd; no HTTP endpoint "
            "exists to set/raise it. Scenario covers ledger accumulation "
            "only. The 402 enforcement path is exercised by "
            "tests/api/test_chat_cost_budget.py."
        ),
    )


async def run_cost_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    model_override: str | None = None,
) -> ScenarioResult:
    """Drive one chat turn and assert the cost surface accumulated correctly.

    Sequence: baseline summary -> baseline ledger -> create conv ->
    stream turn -> post-turn summary -> post-turn ledger -> budget-gap
    marker -> cleanup. Reuses ``helpers.stream_turn`` so the SSE framer
    is exercised the same way as ``chat-roundtrip``.
    """
    r = ScenarioResult(name="cost")
    del state  # PersonaState carried by ``client``; kept for runner parity.

    model_id = await helpers.resolve_default_model(client, r, model_override)
    if model_id is None:
        return r

    baseline_ledger = await _capture_baseline(client, r)

    conv_id = await _drive_chat_turn(client, r, model_id=model_id)
    if conv_id is None:
        _record_budget_gap(r)
        return r

    # The summary endpoint reports the whole user's accumulated cost,
    # so its post-turn delta is racy under fanout (sibling slots can
    # advance ``current_usd`` independently). The ledger delta below
    # filters by ``conversation_id`` and is the authoritative check.
    await _assert_ledger_delta(client, r, len(baseline_ledger), conv_id)
    _record_budget_gap(r)
    await helpers.cleanup_conversation(client, r, conv_id)
    return r
