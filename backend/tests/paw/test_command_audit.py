"""Tests for ``paw audit`` — read-only audit event inspection.

Mocks the backend at the HTTP layer with respx. The persona state is
seeded directly per ``test_command_cost.py`` to keep the test surface
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
AUDIT_ID_A = "11111111-1111-1111-1111-111111111111"
AUDIT_ID_B = "22222222-2222-2222-2222-222222222222"
USER_ID = "33333333-3333-3333-3333-333333333333"


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


def _audit_row(**overrides: Any) -> dict[str, Any]:
    """Build an ``AuditEventRead``-shaped row for respx mocks."""
    base: dict[str, Any] = {
        "id": AUDIT_ID_A,
        "user_id": USER_ID,
        "event_type": "auth.login",
        "success": True,
        "risk_level": "low",
        "details": {"ip": "127.0.0.1"},
        "surface": "web",
        "request_id": "req-abc",
        "created_at": "2026-05-28T10:00:00Z",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# paw audit ls
# --------------------------------------------------------------------------- #


def test_audit_ls_returns_json_rows(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw audit ls --json` round-trips the bare list payload."""
    payload = [_audit_row(), _audit_row(id=AUDIT_ID_B, event_type="chat.turn")]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["audit", "ls", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert isinstance(out, list)
    assert out[0]["id"] == AUDIT_ID_A
    assert out[1]["event_type"] == "chat.turn"


def test_audit_ls_alias_list_works(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw audit list` is a registered alias for `ls`."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[_audit_row()]))
        result = runner.invoke(app, ["audit", "list", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)[0]["id"] == AUDIT_ID_A


def test_audit_ls_forwards_limit_and_offset(runner: CliRunner, seeded: PersonaState) -> None:
    """--limit and --offset are forwarded as query params."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[_audit_row()]))
        result = runner.invoke(app, ["audit", "ls", "--limit", "25", "--offset", "50", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    sent_url = str(route.calls.last.request.url)
    assert "limit=25" in sent_url
    assert "offset=50" in sent_url


def test_audit_ls_forwards_event_type_filter(runner: CliRunner, seeded: PersonaState) -> None:
    """--event-type maps to the documented `event_type` query param."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[_audit_row()]))
        result = runner.invoke(app, ["audit", "ls", "--event-type", "auth.login", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    sent_url = str(route.calls.last.request.url)
    assert "event_type=auth.login" in sent_url


def test_audit_ls_forwards_since_filter(runner: CliRunner, seeded: PersonaState) -> None:
    """--since maps to the documented `since` query param."""
    since = "2026-05-01T00:00:00Z"
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[_audit_row()]))
        result = runner.invoke(app, ["audit", "ls", "--since", since, "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    sent_url = str(route.calls.last.request.url)
    # respx percent-encodes the colon; check the substring without colons.
    assert "since=2026-05-01" in sent_url


def test_audit_ls_omits_unset_filter_params(runner: CliRunner, seeded: PersonaState) -> None:
    """Unset --event-type / --since are NOT sent (avoid silent server-side mismatches)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[_audit_row()]))
        result = runner.invoke(app, ["audit", "ls", "--json"])

    assert result.exit_code == 0, result.stdout
    sent_url = str(route.calls.last.request.url)
    assert "event_type" not in sent_url
    assert "since" not in sent_url


def test_audit_ls_empty_list_succeeds(runner: CliRunner, seeded: PersonaState) -> None:
    """An empty audit log is a normal state, not an error."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[]))
        result = runner.invoke(app, ["audit", "ls", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == []


def test_audit_ls_plain_tsv_shape(runner: CliRunner, seeded: PersonaState) -> None:
    """`--plain` emits one TSV row per event with the expected columns."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[_audit_row()]))
        result = runner.invoke(app, ["audit", "ls", "--plain"])

    assert result.exit_code == 0, result.stdout
    columns = result.stdout.strip().split("\t")
    assert columns[0] == AUDIT_ID_A
    assert columns[2] == "auth.login"
    assert columns[3] == "low"
    assert columns[4] == "true"


def test_audit_ls_human_table_renders(runner: CliRunner, seeded: PersonaState) -> None:
    """Default human view renders an ID/CREATED/EVENT_TYPE/RISK/OK header + rows."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[_audit_row()]))
        result = runner.invoke(app, ["audit", "ls"])

    assert result.exit_code == 0, result.stdout
    assert "ID" in result.stdout
    assert "EVENT_TYPE" in result.stdout
    assert "RISK" in result.stdout
    assert AUDIT_ID_A in result.stdout
    assert "auth.login" in result.stdout


def test_audit_ls_rejects_both_json_and_plain(runner: CliRunner, seeded: PersonaState) -> None:
    """--json + --plain is a usage error (LocalError -> exit 1)."""
    result = runner.invoke(app, ["audit", "ls", "--json", "--plain"])
    assert result.exit_code == 1


def test_audit_ls_rejects_bad_limit(runner: CliRunner, seeded: PersonaState) -> None:
    """Out-of-range --limit is a local error (exit 1) before any HTTP call."""
    result = runner.invoke(app, ["audit", "ls", "--limit", "0"])
    assert result.exit_code == 1
    result = runner.invoke(app, ["audit", "ls", "--limit", "9999"])
    assert result.exit_code == 1


def test_audit_ls_rejects_negative_offset(runner: CliRunner, seeded: PersonaState) -> None:
    """Negative --offset is a local error (exit 1)."""
    result = runner.invoke(app, ["audit", "ls", "--offset", "-1"])
    assert result.exit_code == 1


def test_audit_ls_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["audit", "ls", "--json"])
    assert result.exit_code == 3


def test_audit_ls_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(return_value=httpx.Response(500, json={"detail": "boom"}))
        result = runner.invoke(app, ["audit", "ls", "--json"])
    assert result.exit_code == 5


# --------------------------------------------------------------------------- #
# paw audit show
# --------------------------------------------------------------------------- #


def test_audit_show_returns_matching_event_json(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw audit show <id> --json` returns the matching row from the list response."""
    payload = [_audit_row(), _audit_row(id=AUDIT_ID_B, event_type="chat.turn")]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["audit", "show", AUDIT_ID_B, "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["id"] == AUDIT_ID_B
    assert out["event_type"] == "chat.turn"


def test_audit_show_renders_human_view(runner: CliRunner, seeded: PersonaState) -> None:
    """Default human view renders the event's key fields, including details."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[_audit_row()]))
        result = runner.invoke(app, ["audit", "show", AUDIT_ID_A])

    assert result.exit_code == 0, result.stdout
    assert AUDIT_ID_A in result.stdout
    assert "auth.login" in result.stdout
    assert "risk:" in result.stdout
    assert "details:" in result.stdout


def test_audit_show_not_found_exits_1(runner: CliRunner, seeded: PersonaState) -> None:
    """A missing ID surfaces a LocalError (exit 1) — no per-row endpoint exists."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(return_value=httpx.Response(200, json=[_audit_row()]))
        result = runner.invoke(app, ["audit", "show", AUDIT_ID_B, "--json"])

    assert result.exit_code == 1


def test_audit_show_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 during the underlying list call surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/audit/").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["audit", "show", AUDIT_ID_A, "--json"])
    assert result.exit_code == 3
