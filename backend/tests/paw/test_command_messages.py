"""Tests for ``paw messages`` against a respx-mocked backend."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
CONVERSATION_ID = "conv-1"


def _seed_persona(profile: str = "default") -> PersonaState:
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


def _messages_payload() -> list[dict[str, object]]:
    return [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hi back", "thinking": "computing..."},
    ]


def test_messages_ls_returns_json_list(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/conversations/{CONVERSATION_ID}/messages").mock(
            return_value=httpx.Response(200, json=_messages_payload())
        )
        result = runner.invoke(app, ["messages", "ls", CONVERSATION_ID, "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert len(out) == 2
    assert out[0]["role"] == "user"


def test_messages_get_returns_indexed_row(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/conversations/{CONVERSATION_ID}/messages").mock(
            return_value=httpx.Response(200, json=_messages_payload())
        )
        result = runner.invoke(app, ["messages", "get", CONVERSATION_ID, "1", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["role"] == "assistant"
    assert out["content"] == "hi back"


def test_messages_get_index_out_of_range(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/conversations/{CONVERSATION_ID}/messages").mock(
            return_value=httpx.Response(200, json=_messages_payload())
        )
        result = runner.invoke(app, ["messages", "get", CONVERSATION_ID, "5"])

    assert result.exit_code == 1


def test_messages_ls_404_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/conversations/{CONVERSATION_ID}/messages").mock(
            return_value=httpx.Response(404, json={"detail": "Conversation not found"})
        )
        result = runner.invoke(app, ["messages", "ls", CONVERSATION_ID])

    assert result.exit_code == 5


def test_messages_ls_rejects_json_and_plain_together(
    runner: CliRunner, seeded: PersonaState
) -> None:
    result = runner.invoke(app, ["messages", "ls", CONVERSATION_ID, "--json", "--plain"])
    assert result.exit_code == 1
