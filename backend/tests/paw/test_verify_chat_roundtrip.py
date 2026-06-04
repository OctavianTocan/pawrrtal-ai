"""Tests for ``paw verify chat-roundtrip`` against a respx-mocked backend.

Covers the happy path + four distinct failure modes — one per check
the scenario emits that we want to catch when the backend regresses.

The fixtures intentionally do NOT mock auth endpoints; ``_seed_persona``
writes a logged-in ``PersonaState`` + a non-empty cookie jar so the test
surface stays narrow (we're exercising the scenario, not login).
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

SSE_OK = (
    b'data: {"type": "delta", "content": "Hi"}\n\n'
    b'data: {"type": "delta", "content": " there"}\n\n'
    b'data: {"type": "done"}\n\n'
)
SSE_WITH_TOOL_USE = (
    b'data: {"type": "delta", "content": "Hi"}\n\n'
    b'data: {"type": "tool_use", "name": "search", "input": {}, "tool_use_id": "t1"}\n\n'
    b'data: {"type": "tool_result", "content": "ok", "tool_use_id": "t1"}\n\n'
    b'data: {"type": "delta", "content": " there"}\n\n'
    b'data: {"type": "done"}\n\n'
)
SSE_WITH_THINKING = (
    b'data: {"type": "thinking", "content": "let me think"}\n\n'
    b'data: {"type": "delta", "content": "answer"}\n\n'
    b'data: {"type": "done"}\n\n'
)


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in ``PersonaState`` + a non-empty cookie jar."""
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
            {"model_id": "agent-sdk:anthropic/claude-opus-4-7"},
        ]
    }


def _assistant_row(
    *,
    content: str = "Hi there",
    tool_calls: list[dict[str, Any]] | None = None,
    thinking: str | None = None,
    thinking_duration_seconds: int | None = None,
    assistant_status: str = "complete",
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content,
        "thinking": thinking,
        "tool_calls": tool_calls,
        "timeline": None,
        "thinking_duration_seconds": thinking_duration_seconds,
        "assistant_status": assistant_status,
    }


def _user_row() -> dict[str, Any]:
    return {
        "role": "user",
        "content": "Say hello briefly.",
        "thinking": None,
        "tool_calls": None,
        "timeline": None,
        "thinking_duration_seconds": None,
        "assistant_status": None,
    }


def _mock_happy_path(
    r: respx.MockRouter,
    conv_id: str,
    *,
    sse: bytes = SSE_OK,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    """Wire every endpoint the scenario touches with healthy values."""
    msgs = messages if messages is not None else [_user_row(), _assistant_row()]
    r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_models_payload()))
    r.post(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(
            200,
            json={"id": conv_id, "title": "paw verify chat-roundtrip"},
        )
    )
    r.post("/api/v1/chat/").mock(
        return_value=httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse)
    )
    r.get(f"/api/v1/conversations/{conv_id}/messages").mock(
        return_value=httpx.Response(200, json=msgs)
    )
    r.delete(f"/api/v1/conversations/{conv_id}").mock(return_value=httpx.Response(204))


def _check_names(payload: dict[str, Any]) -> list[str]:
    return [c["name"] for c in payload["checks"] if not c["passed"]]


def test_happy_path_passes_every_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """Stream-vs-DB invariant holds when the backend behaves."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        result = runner.invoke(app, ["verify", "chat-roundtrip", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert _check_names(payload) == []
    names = {c["name"] for c in payload["checks"]}
    assert "content_matches_stream" in names
    assert "tool_call_count_matches_stream" in names
    assert "assistant_status_complete" in names


def test_content_mismatch_fails_content_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A delta in the stream missing from the stored row trips the check."""
    diverged = [_user_row(), _assistant_row(content="totally unrelated reply")]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, messages=diverged)
        result = runner.invoke(app, ["verify", "chat-roundtrip", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "content_matches_stream" in _check_names(payload)


def test_tool_call_count_mismatch_fails(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A ``tool_use`` event with no stored ``tool_calls`` trips the check."""
    no_calls = [_user_row(), _assistant_row(content="Hi there", tool_calls=None)]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, sse=SSE_WITH_TOOL_USE, messages=no_calls)
        result = runner.invoke(app, ["verify", "chat-roundtrip", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "tool_call_count_matches_stream" in _check_names(payload)


def test_thinking_event_without_duration_fails(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A ``thinking`` event with no stored duration trips the positivity check."""
    no_duration = [
        _user_row(),
        _assistant_row(
            content="answer",
            thinking="let me think",
            thinking_duration_seconds=None,
        ),
    ]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, sse=SSE_WITH_THINKING, messages=no_duration)
        result = runner.invoke(app, ["verify", "chat-roundtrip", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "thinking_duration_positive" in _check_names(payload)


def test_assistant_status_not_complete_fails(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A ``streaming`` assistant row trips ``assistant_status_complete``."""
    half_finished = [_user_row(), _assistant_row(assistant_status="streaming")]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, messages=half_finished)
        result = runner.invoke(app, ["verify", "chat-roundtrip", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "assistant_status_complete" in _check_names(payload)


def test_empty_catalog_fails_resolution(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """An empty catalog and no ``--model`` trips ``model_resolved``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(return_value=httpx.Response(200, json={"models": []}))
        result = runner.invoke(app, ["verify", "chat-roundtrip", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "model_resolved" in _check_names(payload)


def test_model_override_skips_catalog_default(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """``--model`` short-circuits the catalog lookup."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        # --model is passed, so the catalog is never fetched.
        r.get("/api/v1/models").mock(
            return_value=httpx.Response(200, json={"models": [{"model_id": DEFAULT_MODEL}]})
        )
        r.post(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json={"id": stable_uuid, "title": "x"})
        )
        r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=SSE_OK
            )
        )
        r.get(f"/api/v1/conversations/{stable_uuid}/messages").mock(
            return_value=httpx.Response(200, json=[_user_row(), _assistant_row()])
        )
        r.delete(f"/api/v1/conversations/{stable_uuid}").mock(return_value=httpx.Response(204))
        result = runner.invoke(
            app, ["verify", "chat-roundtrip", "--model", DEFAULT_MODEL, "--json"]
        )

    assert result.exit_code == 0, result.stdout
