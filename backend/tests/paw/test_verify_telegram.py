"""Tests for ``paw verify telegram`` against a respx-mocked backend."""

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
LINK_CODE = "ABCD-1234"
FUTURE_EXPIRY = "2099-01-01T00:00:00Z"
PAST_EXPIRY = "2000-01-01T00:00:00Z"


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


def _link_code_payload(
    *,
    code: str = LINK_CODE,
    expires_at: str = FUTURE_EXPIRY,
) -> dict[str, Any]:
    """Build a TelegramLinkCodeRead-shaped response."""
    return {
        "code": code,
        "expires_at": expires_at,
        "bot_username": "pawrrtal_bot",
        "deep_link": f"https://t.me/pawrrtal_bot?start={code}",
    }


def _binding_payload() -> dict[str, Any]:
    return {
        "provider": "telegram",
        "external_user_id": "222",
        "external_chat_id": "333",
        "display_handle": "bound",
        "created_at": "2026-05-27T00:00:00Z",
    }


def _diagnostics_payload() -> dict[str, Any]:
    return {
        "configured": True,
        "mode": "polling",
        "runtime": {
            "service_running": True,
            "polling_task": {
                "present": True,
                "done": False,
                "cancelled": False,
                "exception": None,
            },
            "polling_lock_path": "/tmp/pawrrtal-telegram-polling.lock-test",
            "webhook_url_set": False,
            "webhook_secret_set": False,
        },
        "bindings": [_binding_payload()],
        "recent_messages": [],
        "stuck_streaming_messages": [],
        "conversation_trace": None,
    }


def _mock_happy_path(r: respx.MockRouter) -> None:
    """Wire every endpoint the scenario touches to a success response."""
    r.get("/api/v1/channels").mock(return_value=httpx.Response(200, json=[_binding_payload()]))
    r.post("/api/v1/channels/telegram/link").mock(
        return_value=httpx.Response(200, json=_link_code_payload())
    )
    r.post("/api/v1/channels/telegram/simulate").mock(
        return_value=httpx.Response(
            200,
            json={
                "accepted": True,
                "update_id": 123,
                "chat_id": "333",
                "external_user_id": "222",
                "conversation_id": None,
            },
        )
    )
    r.get("/api/v1/channels/telegram/diagnose").mock(
        return_value=httpx.Response(200, json=_diagnostics_payload())
    )


def _check_names(payload: dict[str, Any]) -> list[str]:
    """Names of all failed checks in a JSON-dumped scenario result."""
    return [c["name"] for c in payload["checks"] if not c["passed"]]


def _all_check_names(payload: dict[str, Any]) -> set[str]:
    """Names of every check (passed or failed)."""
    return {c["name"] for c in payload["checks"]}


def test_happy_path_passes_every_check(runner: CliRunner, seeded: PersonaState) -> None:
    """All canonical checks pass when the backend behaves."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r)
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert _check_names(payload) == []
    names = _all_check_names(payload)
    assert {
        "baseline_channels_listed",
        "link_code_issued",
        "link_code_expiry_future",
        "post_issue_channels_listed",
        "telegram_binding_available",
        "telegram_status_command_simulated",
        "telegram_simulate_targets_bound_chat",
        "telegram_diagnostics_available",
        "telegram_runtime_configured",
        "telegram_service_running",
        "telegram_polling_task_running",
    } <= names


def test_baseline_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 on the initial GET surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/channels").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])
    assert result.exit_code == 3, result.stdout


def test_link_issuance_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """A 500 from the link endpoint short-circuits to ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/channels").mock(return_value=httpx.Response(200, json=[]))
        r.post("/api/v1/channels/telegram/link").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 5, result.stdout
    payload = json.loads(result.stdout)
    assert payload["scenario"] == "telegram"
    assert payload["passed"] is False
    assert "POST /api/v1/channels/telegram/link -> 500" in payload["error"]


def test_empty_link_code_fails_issued_check(runner: CliRunner, seeded: PersonaState) -> None:
    """An empty plaintext code trips ``link_code_issued``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r)
        r.post("/api/v1/channels/telegram/link").mock(
            return_value=httpx.Response(200, json=_link_code_payload(code=""))
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "link_code_issued" in _check_names(payload)


def test_past_expiry_fails_expiry_future_check(runner: CliRunner, seeded: PersonaState) -> None:
    """A timestamp in the past trips ``link_code_expiry_future``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r)
        r.post("/api/v1/channels/telegram/link").mock(
            return_value=httpx.Response(200, json=_link_code_payload(expires_at=PAST_EXPIRY))
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "link_code_expiry_future" in _check_names(payload)


def test_missing_binding_fails_simulation_checks(
    runner: CliRunner,
    seeded: PersonaState,
) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/channels").mock(return_value=httpx.Response(200, json=[]))
        r.post("/api/v1/channels/telegram/link").mock(
            return_value=httpx.Response(200, json=_link_code_payload())
        )
        r.get("/api/v1/channels/telegram/diagnose").mock(
            return_value=httpx.Response(200, json=_diagnostics_payload())
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "telegram_binding_available" in _check_names(payload)
    assert "telegram_status_command_simulated" in _check_names(payload)


def test_disabled_simulate_endpoint_fails_status_command_check(
    runner: CliRunner,
    seeded: PersonaState,
) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r)
        r.post("/api/v1/channels/telegram/simulate").mock(
            return_value=httpx.Response(404, json={"detail": "Not Found"})
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "telegram_status_command_simulated" in _check_names(payload)


def test_missing_diagnostics_endpoint_fails_diagnostics_check(
    runner: CliRunner,
    seeded: PersonaState,
) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r)
        r.get("/api/v1/channels/telegram/diagnose").mock(
            return_value=httpx.Response(404, json={"detail": "Not Found"})
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "telegram_diagnostics_available" in _check_names(payload)


def test_configured_bot_without_runtime_fails_service_check(
    runner: CliRunner,
    seeded: PersonaState,
) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r)
        payload = _diagnostics_payload()
        payload["runtime"] = {
            "service_running": False,
            "polling_task": {
                "present": False,
                "done": None,
                "cancelled": None,
                "exception": None,
            },
            "polling_lock_path": None,
            "webhook_url_set": False,
            "webhook_secret_set": False,
        }
        r.get("/api/v1/channels/telegram/diagnose").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 6, result.stdout
    failed = _check_names(json.loads(result.stdout))
    assert "telegram_service_running" in failed
    assert "telegram_polling_task_running" in failed
