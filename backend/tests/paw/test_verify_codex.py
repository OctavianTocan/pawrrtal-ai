"""Tests for ``paw verify codex`` against a respx-mocked backend.

Covers the happy path + five distinct failure modes — one per check
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
from app.cli.paw.verify.codex import CODEX_MODEL

MOCK_BACKEND = "http://test-backend"
FIXED_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
THREAD_ID = "thread-abc"

SSE_OK = (
    b'data: {"type": "delta", "content": "Hi"}\n\n'
    b'data: {"type": "delta", "content": " there"}\n\n'
    b'data: {"type": "done"}\n\n'
)
SSE_ERROR = b'data: {"type": "error", "message": "boom"}\n\ndata: {"type": "done"}\n\n'


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in ``PersonaState`` + a non-empty cookie jar.

    The cookie content doesn't matter — respx intercepts every request
    before it leaves the process — but ``PawClient`` still expects the
    jar file to exist (chmods + reloads on context exit).
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
    """Pin ``ids.new_conversation_id`` to a deterministic value."""
    monkeypatch.setattr("app.cli.paw.ids.new_conversation_id", lambda: FIXED_UUID)
    return FIXED_UUID


def _models_payload() -> dict[str, Any]:
    """Catalog payload with Codex present + authenticated."""
    return {
        "models": [
            {"model_id": CODEX_MODEL, "authenticated": True},
            {"model_id": "openai/gpt-4o", "authenticated": True},
        ]
    }


def _conversation_payload(
    conversation_id: str,
    *,
    model_id: str | None = CODEX_MODEL,
    provider_session_id: str | None = THREAD_ID,
    **overrides: Any,
) -> dict[str, Any]:
    """Minimal ``ConversationRead`` payload for the mocked GET endpoint."""
    base: dict[str, Any] = {
        "id": conversation_id,
        "user_id": "u1",
        "title": "paw verify codex",
        "created_at": "2026-05-27T00:00:00Z",
        "updated_at": "2026-05-27T00:00:00Z",
        "is_archived": False,
        "is_flagged": False,
        "is_unread": False,
        "status": None,
        "model_id": model_id,
        "labels": [],
        "project_id": None,
        "provider_session_id": provider_session_id,
    }
    base.update(overrides)
    return base


def _messages_payload() -> list[dict[str, Any]]:
    """Two persisted messages — a user prompt + a complete assistant reply."""
    return [
        {"role": "user", "content": "Say hi", "assistant_status": None},
        {
            "role": "assistant",
            "content": "Hi there",
            "assistant_status": "complete",
        },
    ]


def _mock_happy_path(r: respx.MockRouter, conv_id: str) -> None:
    """Wire every endpoint the scenario touches to return success values."""
    r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_models_payload()))
    r.post(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(200, json=_conversation_payload(conv_id))
    )
    r.post("/api/v1/chat/").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=SSE_OK
        )
    )
    r.get(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(200, json=_conversation_payload(conv_id))
    )
    r.get(f"/api/v1/conversations/{conv_id}/messages").mock(
        return_value=httpx.Response(200, json=_messages_payload())
    )
    r.delete(f"/api/v1/conversations/{conv_id}").mock(return_value=httpx.Response(204))


def _check_names(payload: dict[str, Any]) -> list[str]:
    """Names of all failed checks in a JSON-dumped scenario result."""
    return [c["name"] for c in payload["checks"] if not c["passed"]]


def test_happy_path_passes_every_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """All eleven checks pass when the backend behaves."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        result = runner.invoke(app, ["verify", "codex", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert _check_names(payload) == []
    # The scenario should emit at least the eleven canonical checks; assert
    # on a couple by name so a future rename surfaces immediately.
    names = {c["name"] for c in payload["checks"]}
    assert "codex_model_in_catalog" in names
    assert "provider_session_id_persisted" in names
    assert "provider_session_id_unchanged_on_resume" in names
    assert "conversation_cleanup" in names


def test_missing_codex_model_fails_catalog_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """Catalog returning no Codex entry trips ``codex_model_in_catalog``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(
            return_value=httpx.Response(200, json={"models": [{"model_id": "openai/gpt-4o"}]})
        )
        result = runner.invoke(app, ["verify", "codex", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert "codex_model_in_catalog" in _check_names(payload)


def test_sse_error_event_fails_turn_1_no_errors(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """An ``error`` event in the stream trips ``turn_1_no_errors``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=SSE_ERROR,
            )
        )
        result = runner.invoke(app, ["verify", "codex", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "turn_1_no_errors" in _check_names(payload)


def test_null_provider_session_id_fails_persistence_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A null ``provider_session_id`` trips ``provider_session_id_persisted``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        r.get(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(
                200, json=_conversation_payload(stable_uuid, provider_session_id=None)
            )
        )
        result = runner.invoke(app, ["verify", "codex", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "provider_session_id_persisted" in _check_names(payload)


def test_changing_thread_id_fails_resume_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A second GET returning a different thread id trips the resume check."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_models_payload()))
        r.post(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conversation_payload(stable_uuid))
        )
        r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=SSE_OK
            )
        )
        # Two GETs: first returns thread-1, second returns thread-2.
        r.get(f"/api/v1/conversations/{stable_uuid}").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json=_conversation_payload(stable_uuid, provider_session_id="thread-1"),
                ),
                httpx.Response(
                    200,
                    json=_conversation_payload(stable_uuid, provider_session_id="thread-2"),
                ),
            ]
        )
        r.get(f"/api/v1/conversations/{stable_uuid}/messages").mock(
            return_value=httpx.Response(200, json=_messages_payload())
        )
        r.delete(f"/api/v1/conversations/{stable_uuid}").mock(return_value=httpx.Response(204))
        result = runner.invoke(app, ["verify", "codex", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "provider_session_id_unchanged_on_resume" in _check_names(payload)


def test_cleanup_500_propagates_api_error(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """Cleanup DELETE returning 500 raises ``ApiError`` (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        r.delete(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        result = runner.invoke(app, ["verify", "codex", "--json"])

    # API error short-circuits before the scenario can mark itself done; exit
    # code is 5 (API error) rather than 6 (verification failed). The plan
    # explicitly calls this out: expect 204 and fail loud if not.
    assert result.exit_code == 5, result.stdout


def test_keep_conversation_skips_delete(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """``--keep-conversation`` records the kept id and never DELETEs."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        delete_route = r.delete(f"/api/v1/conversations/{stable_uuid}")
        result = runner.invoke(app, ["verify", "codex", "--keep-conversation", "--json"])

    assert result.exit_code == 0, result.stdout
    assert delete_route.call_count == 0
    payload = json.loads(result.stdout)
    names = {c["name"] for c in payload["checks"]}
    assert "conversation_kept_per_flag" in names
    assert "conversation_cleanup" not in names
