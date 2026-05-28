"""Tests for ``paw channels`` — third-party messaging channel binding flow.

Mocks the backend at the HTTP layer with respx. The persona state +
cookie jar are seeded directly per ``test_command_workspaces.py`` to
keep the test surface narrow.
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


def _binding_payload(**overrides: Any) -> dict[str, Any]:
    """Build a `ChannelBindingRead`-shaped row for respx mocks."""
    base: dict[str, Any] = {
        "provider": "telegram",
        "external_user_id": "5551234567",
        "external_chat_id": "5551234567",
        "display_handle": "octaviantocan",
        "created_at": "2026-05-27T00:00:00Z",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# paw channels list
# --------------------------------------------------------------------------- #


def test_channels_list_returns_json_bindings(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw channels list --json` round-trips the bare list payload."""
    payload = [_binding_payload()]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/channels").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["channels", "list", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert isinstance(out, list)
    assert out[0]["provider"] == "telegram"
    assert out[0]["display_handle"] == "octaviantocan"


def test_channels_list_empty_list_succeeds(runner: CliRunner, seeded: PersonaState) -> None:
    """An empty bindings list is a normal state, not an error."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/channels").mock(return_value=httpx.Response(200, json=[]))
        result = runner.invoke(app, ["channels", "list", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == []


def test_channels_list_plain_tsv_shape(runner: CliRunner, seeded: PersonaState) -> None:
    """`--plain` emits one TSV row per binding (provider, ext_id, handle, created_at)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/channels").mock(return_value=httpx.Response(200, json=[_binding_payload()]))
        result = runner.invoke(app, ["channels", "list", "--plain"])

    assert result.exit_code == 0, result.stdout
    columns = result.stdout.strip().split("\t")
    assert columns[0] == "telegram"
    assert columns[1] == "5551234567"
    assert columns[2] == "octaviantocan"


def test_channels_list_rejects_both_json_and_plain(runner: CliRunner, seeded: PersonaState) -> None:
    """--json + --plain is a usage error (LocalError -> exit 1)."""
    result = runner.invoke(app, ["channels", "list", "--json", "--plain"])
    assert result.exit_code == 1


def test_channels_list_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/channels").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["channels", "list", "--json"])
    assert result.exit_code == 3


# --------------------------------------------------------------------------- #
# paw channels link telegram
# --------------------------------------------------------------------------- #


def test_channels_link_telegram_returns_code(runner: CliRunner, seeded: PersonaState) -> None:
    """`link telegram --json` returns the full TelegramLinkCodeRead envelope."""
    code_payload = {
        "code": "ABCD-1234",
        "expires_at": "2026-05-27T01:00:00Z",
        "bot_username": "pawrrtal_bot",
        "deep_link": "https://t.me/pawrrtal_bot?start=ABCD-1234",
    }
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.post("/api/v1/channels/telegram/link").mock(
            return_value=httpx.Response(200, json=code_payload)
        )
        result = runner.invoke(app, ["channels", "link", "telegram", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    out = json.loads(result.stdout)
    assert out["code"] == "ABCD-1234"
    assert out["bot_username"] == "pawrrtal_bot"
    assert out["deep_link"].endswith("ABCD-1234")


def test_channels_link_telegram_503_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """503 (Telegram not configured) surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.post("/api/v1/channels/telegram/link").mock(
            return_value=httpx.Response(503, json={"detail": "Telegram channel is not configured."})
        )
        result = runner.invoke(app, ["channels", "link", "telegram"])
    assert result.exit_code == 5


# --------------------------------------------------------------------------- #
# paw channels unlink telegram
# --------------------------------------------------------------------------- #


def test_channels_unlink_telegram_requires_yes(runner: CliRunner, seeded: PersonaState) -> None:
    """Without --yes the command is a LocalError (exit 1)."""
    result = runner.invoke(app, ["channels", "unlink", "telegram"])
    assert result.exit_code == 1


def test_channels_unlink_telegram_204_succeeds(runner: CliRunner, seeded: PersonaState) -> None:
    """A 204 (whether or not a binding existed) is exit 0 with unlinked=True."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.delete("/api/v1/channels/telegram/link").mock(return_value=httpx.Response(204))
        result = runner.invoke(app, ["channels", "unlink", "telegram", "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    out = json.loads(result.stdout)
    assert out == {"unlinked": True, "provider": "telegram"}


def test_channels_unlink_telegram_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete("/api/v1/channels/telegram/link").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        result = runner.invoke(app, ["channels", "unlink", "telegram", "--yes"])
    assert result.exit_code == 5
