"""Tests for ``paw verify google-chat`` against a respx-mocked backend.

The Google Chat channel has no HTTP surface, so the scenario pings the
backend for liveness and then asserts the channel's pure logic (Markdown→Chat
formatting, slash-command parsing, field extraction, registration). These
tests mock only the health ping; the channel-logic checks run in-process.
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

# Every check the scenario emits — pinned so a rename surfaces immediately.
_CANONICAL_CHECKS = {
    "backend_reachable",
    "channel_registered",
    "bold_to_single_asterisk",
    "heading_to_bold",
    "link_to_angle_pipe",
    "no_raw_double_asterisk",
    "slash_command_parsed",
    "slash_command_args_parsed",
    "non_command_ignored",
    "event_fields_extracted",
    "live_pubsub_roundtrip_bot_covered",
}


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in PersonaState + non-empty cookie jar."""
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


def _failed_names(payload: dict[str, Any]) -> list[str]:
    return [c["name"] for c in payload["checks"] if not c["passed"]]


def test_happy_path_passes_every_check(runner: CliRunner, seeded: PersonaState) -> None:
    """With the backend live, every check — including the formatting guards — passes."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
        result = runner.invoke(app, ["verify", "google-chat", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert _failed_names(payload) == []
    names = {c["name"] for c in payload["checks"]}
    assert names >= _CANONICAL_CHECKS


def test_formatting_checks_assert_conversion(runner: CliRunner, seeded: PersonaState) -> None:
    """The markup-leak guards assert the exact Chat-syntax conversions."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
        result = runner.invoke(app, ["verify", "google-chat", "--json"])

    payload = json.loads(result.stdout)
    by_name = {c["name"]: c for c in payload["checks"]}
    assert by_name["bold_to_single_asterisk"]["passed"]
    assert by_name["heading_to_bold"]["passed"]
    assert by_name["link_to_angle_pipe"]["passed"]
    assert by_name["no_raw_double_asterisk"]["passed"]
    assert by_name["slash_command_parsed"]["passed"]


def test_backend_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """A 5xx on the liveness ping surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/health").mock(return_value=httpx.Response(500, json={"detail": "boom"}))
        result = runner.invoke(app, ["verify", "google-chat", "--json"])
    assert result.exit_code == 5, result.stdout


def test_backend_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 on the liveness ping surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/health").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["verify", "google-chat", "--json"])
    assert result.exit_code == 3, result.stdout
