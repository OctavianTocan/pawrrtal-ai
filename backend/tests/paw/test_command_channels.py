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
from app.infrastructure.config import settings

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


def test_channels_send_telegram_posts_to_bot_api(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator send command calls Telegram directly and returns message_id."""
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")
    payload = {"ok": True, "result": {"message_id": 1703, "chat": {"id": 8070668819}}}
    with respx.mock(base_url="https://api.telegram.org", assert_all_called=False) as r:
        route = r.post("/bottest-token/sendMessage").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(
            app,
            [
                "channels",
                "send",
                "telegram",
                "--chat-id",
                "8070668819",
                "--text",
                "hello",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    assert route.called
    out = json.loads(result.stdout)
    assert out["message_id"] == 1703
    assert out["chat_id"] == "8070668819"


def test_channels_send_telegram_requires_single_target(runner: CliRunner) -> None:
    """Exactly one target selector is required."""
    result = runner.invoke(
        app,
        [
            "channels",
            "send",
            "telegram",
            "--chat-id",
            "1",
            "--user-email",
            "a@example.com",
            "--text",
            "hello",
        ],
    )
    assert result.exit_code == 1


def test_channels_diagnose_telegram_reports_stuck_streams(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local Telegram diagnostic command summarizes stuck assistant turns."""

    async def fake_diagnose(*, limit: int, conversation_id: str | None = None) -> dict[str, Any]:
        assert conversation_id is None
        return {
            "configured": True,
            "mode": "polling",
            "bindings": [],
            "recent_messages": [],
            "stuck_streaming_messages": [
                {
                    "created_at": "2026-05-30T20:57:59",
                    "conversation_id": "853434fb5f094b588598c0384e4fdc22",
                    "ordinal": 9,
                    "model_id": "openai-codex:openai/gpt-5.5",
                }
            ],
            "conversation_trace": None,
        }

    monkeypatch.setattr("app.cli.paw.commands.channels._diagnose_telegram", fake_diagnose)

    result = runner.invoke(app, ["channels", "diagnose-telegram"])

    assert result.exit_code == 0, result.stdout
    assert "stuck_streaming_messages: 1" in result.stdout
    assert "conversation=853434fb5f094b588598c0384e4fdc22" in result.stdout


def test_channels_diagnose_telegram_can_focus_conversation(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The diagnostic command can include a conversation/thread trace."""
    conversation_id = "853434fb-5f09-4b58-8598-c0384e4fdc22"

    async def fake_diagnose(*, limit: int, conversation_id: str | None = None) -> dict[str, Any]:
        assert limit == 10
        return {
            "configured": True,
            "mode": "polling",
            "bindings": [],
            "recent_messages": [],
            "stuck_streaming_messages": [],
            "conversation_trace": {
                "conversation_id": conversation_id,
                "model_id": "openai-codex:openai/gpt-5.5",
                "provider_session_id": "thr_123",
                "workspace_skill_prompt_mode": "manifest",
                "recent_usage": [
                    {
                        "created_at": "2026-05-30T21:00:01",
                        "input_tokens": 97,
                        "output_tokens": 3,
                        "cost_usd": 0.001,
                        "model_id": "openai-codex:openai/gpt-5.5",
                    }
                ],
                "messages": [
                    {
                        "created_at": "2026-05-30T21:00:00",
                        "ordinal": 2,
                        "role": "ai",
                        "assistant_status": "complete",
                        "duration_ms": 1200,
                        "timeline_count": 7,
                        "thinking_chars": 42,
                        "content_preview": "done",
                    }
                ],
            },
        }

    monkeypatch.setattr("app.cli.paw.commands.channels._diagnose_telegram", fake_diagnose)

    result = runner.invoke(
        app,
        ["channels", "diagnose-telegram", "--conversation-id", conversation_id],
    )

    assert result.exit_code == 0, result.stdout
    assert "provider_session_id: thr_123" in result.stdout
    assert "skill_prompt_mode: manifest" in result.stdout
    assert "in=97" in result.stdout
    assert "duration_ms=1200" in result.stdout
    assert "timeline=7" in result.stdout


def test_admin_seed_user_rejects_partial_telegram_options() -> None:
    """Telegram bootstrap options must include the provider user id."""
    from app.cli.paw.commands.admin import _validate_telegram_options
    from app.cli.paw.errors import LocalError

    with pytest.raises(LocalError):
        _validate_telegram_options(
            telegram_id=None,
            telegram_chat_id="8070668819",
            telegram_handle=None,
            claim_telegram=False,
        )
