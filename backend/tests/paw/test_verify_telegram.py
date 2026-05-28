"""Tests for ``paw verify telegram`` against a respx-mocked backend.

Covers the happy path + the failure modes for every check the scenario
emits. The link-code lifecycle is the full scope today; the bot-side
redemption hop is documented as a passing
``simulate_redemption_endpoint_unavailable`` check.
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


def _mock_happy_path(r: respx.MockRouter) -> None:
    """Wire every endpoint the scenario touches to a success response."""
    r.get("/api/v1/channels").mock(return_value=httpx.Response(200, json=[]))
    r.post("/api/v1/channels/telegram/link").mock(
        return_value=httpx.Response(200, json=_link_code_payload())
    )
    r.delete("/api/v1/channels/telegram/link").mock(return_value=httpx.Response(204))


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
    # Pin every canonical name so a future rename surfaces immediately.
    assert {
        "baseline_channels_listed",
        "link_code_issued",
        "link_code_expiry_future",
        "post_issue_channels_listed",
        "simulate_redemption_endpoint_unavailable",
        "telegram_unlinked",
        "telegram_binding_absent_after_unlink",
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


def test_unlink_500_propagates_api_error(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 on DELETE surfaces as ApiError (exit 5).

    The backend route is documented as idempotent 204, so any non-204
    response is a real backend regression, not a soft-pass case.
    """
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r)
        r.delete("/api/v1/channels/telegram/link").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 5, result.stdout


def test_lingering_telegram_binding_fails_post_unlink_check(
    runner: CliRunner, seeded: PersonaState
) -> None:
    """A telegram binding still present after DELETE trips the absent-after check."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.post("/api/v1/channels/telegram/link").mock(
            return_value=httpx.Response(200, json=_link_code_payload())
        )
        r.delete("/api/v1/channels/telegram/link").mock(return_value=httpx.Response(204))
        # Baseline + post-issue list return empty; post-unlink list still
        # reports a telegram binding (a backend bug we want to catch).
        r.get("/api/v1/channels").mock(
            side_effect=[
                httpx.Response(200, json=[]),
                httpx.Response(200, json=[]),
                httpx.Response(
                    200,
                    json=[
                        {
                            "provider": "telegram",
                            "external_user_id": "5551234567",
                            "external_chat_id": "5551234567",
                            "display_handle": "octaviantocan",
                            "created_at": "2026-05-28T00:00:00Z",
                        }
                    ],
                ),
            ]
        )
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "telegram_binding_absent_after_unlink" in _check_names(payload)


def test_simulate_gap_check_is_recorded_and_passes(runner: CliRunner, seeded: PersonaState) -> None:
    """The missing-simulate-endpoint check ships as a stable, passing marker.

    Consumers (CI dashboards, agents) grep for the name to spot the gap;
    the day a simulate endpoint lands, this check should be replaced
    with real bot-side redemption assertions.
    """
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r)
        result = runner.invoke(app, ["verify", "telegram", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    sim_check = next(
        (c for c in payload["checks"] if c["name"] == "simulate_redemption_endpoint_unavailable"),
        None,
    )
    assert sim_check is not None
    assert sim_check["passed"] is True
    assert "simulate" in sim_check["detail"].lower()
