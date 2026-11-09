"""Tests for ``paw cost`` — cost summary + ledger.

Mocks the backend at the HTTP layer with respx. The persona state is
seeded directly per ``test_command_mcp.py`` to keep the test surface
narrow.
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
LEDGER_ROW_ID_A = "11111111-1111-1111-1111-111111111111"
LEDGER_ROW_ID_B = "22222222-2222-2222-2222-222222222222"
CONVERSATION_ID = "33333333-3333-3333-3333-333333333333"


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in PersonaState rooted at the respx mock backend."""
    state = PersonaState(
        profile=profile,
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="admin@example.com",
    )
    state.save()
    jar = load_cookies(cookies_path(profile))
    save_cookies(jar, cookies_path(profile))
    return state


@pytest.fixture
def seeded() -> PersonaState:
    return _seed_persona()


def _summary_payload(**overrides: Any) -> dict[str, Any]:
    """Build a ``CostSummaryRead``-shaped body for respx mocks."""
    base: dict[str, Any] = {
        "window_hours": 24,
        "current_usd": 1.2345,
        "limit_usd": 10.0,
        "remaining_usd": 8.7655,
        "per_model": None,
    }
    base.update(overrides)
    return base


def _ledger_row(**overrides: Any) -> dict[str, Any]:
    """Build a ``CostLedgerRead``-shaped row for respx mocks."""
    base: dict[str, Any] = {
        "id": LEDGER_ROW_ID_A,
        "conversation_id": CONVERSATION_ID,
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": 0.0042,
        "surface": "chat",
        "created_at": "2026-05-28T10:00:00Z",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# paw cost summary
# --------------------------------------------------------------------------- #


def test_cost_summary_returns_json_envelope(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw cost summary --json` round-trips the CostSummaryRead body."""
    payload = _summary_payload()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["cost", "summary", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["window_hours"] == 24
    assert out["current_usd"] == pytest.approx(1.2345)
    assert out["limit_usd"] == pytest.approx(10.0)


def test_cost_summary_forwards_window_and_breakdown(
    runner: CliRunner, seeded: PersonaState
) -> None:
    """`--window-hours` + `--by model` map to the documented query params."""
    payload = _summary_payload(
        window_hours=6,
        per_model=[{"model_id": "gpt-4o-mini", "cost_usd": 0.5, "turns": 3}],
    )
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.get("/api/v1/cost/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(
            app, ["cost", "summary", "--window-hours", "6", "--by", "model", "--json"]
        )

    assert result.exit_code == 0, result.stdout
    assert route.called
    sent_url = str(route.calls.last.request.url)
    assert "window_hours=6" in sent_url
    assert "breakdown=true" in sent_url
    out = json.loads(result.stdout)
    assert out["per_model"][0]["model_id"] == "gpt-4o-mini"


def test_cost_summary_plain_tsv_shape(runner: CliRunner, seeded: PersonaState) -> None:
    """`--plain` emits one TSV row per scalar field, then per_model entries."""
    payload = _summary_payload(per_model=[{"model_id": "gpt-4o-mini", "cost_usd": 0.5, "turns": 3}])
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["cost", "summary", "--by", "model", "--plain"])

    assert result.exit_code == 0, result.stdout
    lines = [line for line in result.stdout.splitlines() if line]
    # Four scalar rows + one per_model row.
    assert len(lines) == 5
    assert lines[0].split("\t")[0] == "window_hours"
    assert lines[-1].split("\t")[0] == "per_model"
    assert lines[-1].split("\t")[1] == "gpt-4o-mini"


def test_cost_summary_human_default_renders(runner: CliRunner, seeded: PersonaState) -> None:
    """Default (human) mode renders the window/current/limit lines."""
    payload = _summary_payload()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["cost", "summary"])

    assert result.exit_code == 0, result.stdout
    assert "window: 24h" in result.stdout
    assert "current:" in result.stdout
    assert "$1.2345" in result.stdout


def test_cost_summary_human_handles_no_limit(runner: CliRunner, seeded: PersonaState) -> None:
    """When limit_usd is None, render the row as ``unlimited`` (not ``$None``)."""
    payload = _summary_payload(limit_usd=None, remaining_usd=None)
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["cost", "summary"])

    assert result.exit_code == 0, result.stdout
    assert "unlimited" in result.stdout


def test_cost_summary_rejects_both_json_and_plain(runner: CliRunner, seeded: PersonaState) -> None:
    """--json + --plain is a usage error (LocalError -> exit 1)."""
    result = runner.invoke(app, ["cost", "summary", "--json", "--plain"])
    assert result.exit_code == 1


def test_cost_summary_rejects_bad_window_hours(runner: CliRunner, seeded: PersonaState) -> None:
    """Out-of-range --window-hours is a local error (exit 1) before any HTTP call."""
    result = runner.invoke(app, ["cost", "summary", "--window-hours", "0"])
    assert result.exit_code == 1
    result = runner.invoke(app, ["cost", "summary", "--window-hours", "99999"])
    assert result.exit_code == 1


def test_cost_summary_rejects_bad_breakdown_axis(runner: CliRunner, seeded: PersonaState) -> None:
    """An unsupported --by axis is a local error (exit 1)."""
    result = runner.invoke(app, ["cost", "summary", "--by", "workspace"])
    assert result.exit_code == 1


def test_cost_summary_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["cost", "summary", "--json"])
    assert result.exit_code == 3


def test_cost_summary_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/").mock(return_value=httpx.Response(500, json={"detail": "boom"}))
        result = runner.invoke(app, ["cost", "summary", "--json"])
    assert result.exit_code == 5


# --------------------------------------------------------------------------- #
# paw cost ledger
# --------------------------------------------------------------------------- #


def test_cost_ledger_returns_json_rows(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw cost ledger --json` round-trips the bare list payload."""
    payload = [_ledger_row(), _ledger_row(id=LEDGER_ROW_ID_B, provider="anthropic")]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/ledger").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["cost", "ledger", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert isinstance(out, list)
    assert out[0]["id"] == LEDGER_ROW_ID_A
    assert out[1]["provider"] == "anthropic"


def test_cost_ledger_forwards_limit_and_offset(runner: CliRunner, seeded: PersonaState) -> None:
    """--limit and --offset are forwarded as query params."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.get("/api/v1/cost/ledger").mock(
            return_value=httpx.Response(200, json=[_ledger_row()])
        )
        result = runner.invoke(app, ["cost", "ledger", "--limit", "25", "--offset", "50", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    sent_url = str(route.calls.last.request.url)
    assert "limit=25" in sent_url
    assert "offset=50" in sent_url


def test_cost_ledger_empty_list_succeeds(runner: CliRunner, seeded: PersonaState) -> None:
    """An empty ledger is a normal state, not an error."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/ledger").mock(return_value=httpx.Response(200, json=[]))
        result = runner.invoke(app, ["cost", "ledger", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == []


def test_cost_ledger_plain_tsv_shape(runner: CliRunner, seeded: PersonaState) -> None:
    """`--plain` emits one TSV row per ledger entry (id, created_at, provider, ...)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/ledger").mock(return_value=httpx.Response(200, json=[_ledger_row()]))
        result = runner.invoke(app, ["cost", "ledger", "--plain"])

    assert result.exit_code == 0, result.stdout
    columns = result.stdout.strip().split("\t")
    assert columns[0] == LEDGER_ROW_ID_A
    assert columns[2] == "openai"
    assert columns[3] == "gpt-4o-mini"


def test_cost_ledger_human_table_renders(runner: CliRunner, seeded: PersonaState) -> None:
    """Default human view renders an ID/PROVIDER/MODEL header + each row."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/ledger").mock(return_value=httpx.Response(200, json=[_ledger_row()]))
        result = runner.invoke(app, ["cost", "ledger"])

    assert result.exit_code == 0, result.stdout
    assert "ID" in result.stdout
    assert "PROVIDER" in result.stdout
    assert LEDGER_ROW_ID_A in result.stdout
    assert "openai" in result.stdout


def test_cost_ledger_rejects_both_json_and_plain(runner: CliRunner, seeded: PersonaState) -> None:
    """--json + --plain is a usage error (LocalError -> exit 1)."""
    result = runner.invoke(app, ["cost", "ledger", "--json", "--plain"])
    assert result.exit_code == 1


def test_cost_ledger_rejects_bad_limit(runner: CliRunner, seeded: PersonaState) -> None:
    """Out-of-range --limit is a local error (exit 1) before any HTTP call."""
    result = runner.invoke(app, ["cost", "ledger", "--limit", "0"])
    assert result.exit_code == 1
    result = runner.invoke(app, ["cost", "ledger", "--limit", "9999"])
    assert result.exit_code == 1


def test_cost_ledger_rejects_negative_offset(runner: CliRunner, seeded: PersonaState) -> None:
    """Negative --offset is a local error (exit 1)."""
    result = runner.invoke(app, ["cost", "ledger", "--offset", "-1"])
    assert result.exit_code == 1


def test_cost_ledger_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/ledger").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["cost", "ledger", "--json"])
    assert result.exit_code == 3


def test_cost_ledger_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/cost/ledger").mock(return_value=httpx.Response(500, json={"detail": "boom"}))
        result = runner.invoke(app, ["cost", "ledger", "--json"])
    assert result.exit_code == 5
