"""Tests for ``paw verify cost`` against a respx-mocked backend.

Covers the happy path + the failure modes for every check the scenario
emits. The ledger-accumulation lifecycle is the full scope today; the
per-user budget-setter endpoint does not exist, so the missing-endpoint
marker check is asserted as a stable passing row.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
FIXED_UUID = "11111111-2222-3333-4444-555555555555"
DEFAULT_MODEL = "openai-codex:openai/gpt-5.5"

# One healthy chat stream — two delta events + done sentinel. Mirrors
# the SSE_OK fixture in test_verify_chat_roundtrip.py.
SSE_OK = (
    b'data: {"type": "delta", "content": "Hi"}\n\n'
    b'data: {"type": "delta", "content": " there"}\n\n'
    b'data: {"type": "done"}\n\n'
)

# Baseline summary: $1.23 used out of $100 cap.
BASELINE_CURRENT_USD = 1.23

# Per-turn cost reported on the new ledger row.
TURN_COST_USD = 0.22


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in PersonaState + non-empty cookie jar.

    Cookie content doesn't matter — respx intercepts every request — but
    ``PawClient`` still expects the jar file to exist.
    """
    state = PersonaState(
        profile=profile,
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="admin@example.com",
        default_workspace_id="ws-1",
    )
    state.save()
    jar = load_cookies(cookies_path(profile))
    save_cookies(jar, cookies_path(profile))
    return state


@pytest.fixture
def seeded() -> PersonaState:
    return _seed_persona()


@pytest.fixture
def stable_uuid(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("app.cli.paw.ids.new_conversation_id", lambda: FIXED_UUID)
    return FIXED_UUID


def _models_payload() -> dict[str, Any]:
    return {
        "models": [
            {"model_id": DEFAULT_MODEL, "id": DEFAULT_MODEL},
        ]
    }


def _summary(current_usd: float) -> dict[str, Any]:
    """Build a CostSummaryRead-shaped envelope."""
    return {
        "window_hours": 24,
        "current_usd": current_usd,
        "limit_usd": 100.0,
        "remaining_usd": 100.0 - current_usd,
        "per_model": None,
    }


def _ledger_row(
    *,
    conversation_id: str | None = FIXED_UUID,
    cost_usd: float = TURN_COST_USD,
    row_id: str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
) -> dict[str, Any]:
    """Build a CostLedgerRead-shaped row."""
    return {
        "id": row_id,
        "conversation_id": conversation_id,
        "provider": "openai-codex",
        "model_id": DEFAULT_MODEL,
        "input_tokens": 10,
        "output_tokens": 20,
        "cost_usd": cost_usd,
        "surface": "chat",
        "created_at": "2026-05-28T00:00:00Z",
    }


def _mock_happy_path(
    r: respx.MockRouter,
    conv_id: str,
    *,
    sse: bytes = SSE_OK,
    baseline_ledger: list[dict[str, Any]] | None = None,
    post_turn_ledger: list[dict[str, Any]] | None = None,
    baseline_summary: dict[str, Any] | None = None,
) -> None:
    """Wire every endpoint the scenario touches to a healthy response.

    The summary endpoint is hit once (baseline only) — the scenario no
    longer compares ``current_usd`` across the turn because that summary
    is racy under fanout. The conversation-scoped ledger delta is the
    authoritative check.
    """
    base_ledger = baseline_ledger if baseline_ledger is not None else []
    post_ledger = (
        post_turn_ledger if post_turn_ledger is not None else [_ledger_row(conversation_id=conv_id)]
    )
    base_summary = baseline_summary or _summary(BASELINE_CURRENT_USD)

    r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_models_payload()))
    r.get("/api/v1/cost/").mock(return_value=httpx.Response(200, json=base_summary))
    r.get("/api/v1/cost/ledger").mock(
        side_effect=[
            httpx.Response(200, json=base_ledger),
            httpx.Response(200, json=post_ledger),
        ]
    )
    r.post(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(200, json={"id": conv_id, "title": "paw verify cost"})
    )
    r.post("/api/v1/chat/").mock(
        return_value=httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse)
    )
    r.delete(f"/api/v1/conversations/{conv_id}").mock(return_value=httpx.Response(204))


def _failed_check_names(payload: dict[str, Any]) -> list[str]:
    """Names of all failed checks in a JSON-dumped scenario result."""
    return [c["name"] for c in payload["checks"] if not c["passed"]]


def _all_check_names(payload: dict[str, Any]) -> set[str]:
    """Names of every check (passed or failed)."""
    return {c["name"] for c in payload["checks"]}


def test_happy_path_passes_every_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """All canonical checks pass when the backend behaves."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        result = runner.invoke(app, ["verify", "cost", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert _failed_check_names(payload) == []
    names = _all_check_names(payload)
    # Pin every canonical name so a future rename surfaces immediately.
    assert {
        "model_resolved",
        "baseline_summary",
        "baseline_ledger_size",
        "conversation_created",
        "chat_turn_no_errors",
        "chat_turn_final_text_nonempty",
        "ledger_row_added",
        "ledger_row_references_conversation",
        "ledger_row_cost_nonzero",
        "budget_endpoint_unavailable",
        "conversation_cleanup",
    } <= names
    # ``summary_current_usd_increased`` was retired: the summary endpoint
    # reports the whole user, which races under fanout. The
    # conversation-scoped ledger checks are the authoritative delta.
    assert "summary_current_usd_increased" not in names


def test_baseline_401_exits_3(runner: CliRunner, seeded: PersonaState, stable_uuid: str) -> None:
    """A 401 on the initial GET surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_models_payload()))
        r.get("/api/v1/cost/").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["verify", "cost", "--json"])
    assert result.exit_code == 3, result.stdout


def test_no_new_ledger_row_fails_added_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """Ledger row count unchanged after the turn trips ``ledger_row_added``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, baseline_ledger=[], post_turn_ledger=[])
        result = runner.invoke(app, ["verify", "cost", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    failed = _failed_check_names(payload)
    assert "ledger_row_added" in failed


def test_ledger_row_missing_conversation_id_fails(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A new ledger row that doesn't reference the new conversation trips the check."""
    orphan_row = _ledger_row(conversation_id="00000000-0000-0000-0000-000000000000")
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(
            r,
            stable_uuid,
            baseline_ledger=[],
            post_turn_ledger=[orphan_row],
        )
        result = runner.invoke(app, ["verify", "cost", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "ledger_row_references_conversation" in _failed_check_names(payload)


def test_ledger_row_zero_cost_fails(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A new ledger row with ``cost_usd=0`` trips ``ledger_row_cost_nonzero``."""
    zero_row = _ledger_row(cost_usd=0.0)
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(
            r,
            stable_uuid,
            baseline_ledger=[],
            post_turn_ledger=[zero_row],
        )
        result = runner.invoke(app, ["verify", "cost", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "ledger_row_cost_nonzero" in _failed_check_names(payload)


def test_budget_gap_check_is_recorded_and_passes(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """The missing-budget-endpoint check ships as a stable, passing marker.

    Consumers (CI dashboards, agents) grep for the name to spot the gap;
    the day a per-user budget setter lands, this check should be
    replaced with real enforcement assertions.
    """
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        result = runner.invoke(app, ["verify", "cost", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    marker = next(
        (c for c in payload["checks"] if c["name"] == "budget_endpoint_unavailable"),
        None,
    )
    assert marker is not None
    assert marker["passed"] is True
    assert "budget" in marker["detail"].lower()


def test_json_shape_matches_scenario_result(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """``--json`` emits the canonical ScenarioResult shape."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        result = runner.invoke(app, ["verify", "cost", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["scenario"] == "cost"
    assert isinstance(payload["passed"], bool)
    assert isinstance(payload["checks"], list)
    assert isinstance(payload["artifacts"], dict)
    # Every artifact key we promise to emit on the happy path.
    assert "baseline_summary" in payload["artifacts"]
    assert "baseline_ledger_count" in payload["artifacts"]
    assert "post_turn_ledger_count" in payload["artifacts"]
    assert "chat_events" in payload["artifacts"]


def test_empty_final_text_short_circuits_with_budget_marker(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A stream with no text events fails the final-text check and still emits the marker."""
    empty_sse = b'data: {"type": "done"}\n\n'
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, sse=empty_sse)
        result = runner.invoke(app, ["verify", "cost", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    failed = _failed_check_names(payload)
    assert "chat_turn_final_text_nonempty" in failed
    # Marker still emitted even on short-circuit so downstream tooling
    # can grep for the gap regardless of upstream chat health.
    assert "budget_endpoint_unavailable" in _all_check_names(payload)
