"""Tests for ``paw conversations`` against a respx-mocked backend.

The fixtures here intentionally do NOT mock the auth endpoints — every
test seeds a ``PersonaState`` + cookie jar directly via ``_login`` so
the test surface stays narrow (we're exercising the conversations
commands, not the login flow).
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
NEW_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in PersonaState + a non-empty cookie jar.

    The cookie content doesn't matter for these tests — respx intercepts
    every request before it leaves the process — but PawClient still
    expects the jar file to exist (it chmods + reloads on context exit).
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
    monkeypatch.setattr("app.cli.paw.ids.new_conversation_id", lambda: NEW_UUID)
    return NEW_UUID


def _conversation_payload(conversation_id: str, **overrides: Any) -> dict[str, Any]:
    """Minimal ConversationRead-shaped payload."""
    base: dict[str, Any] = {
        "id": conversation_id,
        "user_id": "u1",
        "title": "Untitled",
        "created_at": "2026-05-27T00:00:00Z",
        "updated_at": "2026-05-27T00:00:00Z",
        "is_archived": False,
        "is_flagged": False,
        "is_unread": False,
        "status": None,
        "model_id": "gpt-4o",
        "labels": [],
        "project_id": None,
        "provider_session_id": None,
    }
    base.update(overrides)
    return base


def test_create_posts_to_uuid_endpoint_and_persists_state(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """`paw conversations create --json` POSTs to /conversations/{uuid} and saves state."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        post = r.post(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(
                200, json=_conversation_payload(stable_uuid, title="Q2 planning")
            )
        )
        result = runner.invoke(app, ["conversations", "create", "--title", "Q2 planning", "--json"])

    assert result.exit_code == 0, result.stdout
    assert post.called
    out = json.loads(result.stdout)
    assert out["id"] == stable_uuid
    assert out["title"] == "Q2 planning"

    # State must remember the new conversation as current.
    reloaded = PersonaState.load("default")
    assert reloaded.current_conversation_id == stable_uuid


def test_send_new_streams_sse_and_fetches_provider_session_id(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """`paw conversations send 'hi' --new --json` runs the full create+chat+followup flow."""
    sse_body = (
        b'data: {"type": "delta", "content": "Hi"}\n\n'
        b'data: {"type": "delta", "content": " there"}\n\n'
        b'data: {"type": "usage", "input_tokens": 5, "output_tokens": 2}\n\n'
        b"data: [DONE]\n\n"
    )
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        models_route = r.get("/api/v1/models").mock(
            return_value=httpx.Response(
                200, json={"models": [{"model_id": "litellm:openai/gpt-4o-mini"}]}
            )
        )
        create_route = r.post(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conversation_payload(stable_uuid))
        )
        chat_route = r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse_body,
            )
        )
        r.get(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(
                200,
                json=_conversation_payload(stable_uuid, provider_session_id="thread-abc"),
            )
        )
        result = runner.invoke(
            app,
            ["conversations", "send", "hi", "--new", "--json"],
        )

    assert result.exit_code == 0, result.stdout
    assert models_route.called, "new conversations need an explicit chat model"
    assert create_route.called, "must create the conversation row before chat"
    assert chat_route.called
    assert json.loads(chat_route.calls.last.request.content)["model_id"] == (
        "litellm:openai/gpt-4o-mini"
    )
    out = json.loads(result.stdout)
    assert out["conversation_id"] == stable_uuid
    assert out["provider_session_id"] == "thread-abc"
    assert out["final_text"] == "Hi there"
    assert out["events"]["delta"] == 2
    assert out["events"]["usage"] == 1


def test_send_new_with_model_skips_catalog_lookup(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """An explicit --model is forwarded without fetching the catalog."""
    sse_body = b'data: {"type": "delta", "content": "Hi"}\n\ndata: [DONE]\n\n'
    explicit_model = "agent-sdk:anthropic/claude-opus-4-7"
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        models_route = r.get("/api/v1/models").mock(
            return_value=httpx.Response(500, json={"detail": "should not be called"})
        )
        r.post(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conversation_payload(stable_uuid))
        )
        chat_route = r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse_body,
            )
        )
        r.get(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conversation_payload(stable_uuid))
        )
        result = runner.invoke(
            app,
            ["conversations", "send", "hi", "--new", "--model", explicit_model, "--json"],
        )

    assert result.exit_code == 0, result.stdout
    assert not models_route.called
    assert json.loads(chat_route.calls.last.request.content)["model_id"] == explicit_model


def test_send_existing_unpinned_conversation_resolves_model(
    runner: CliRunner, seeded: PersonaState
) -> None:
    """Existing conversations with no pinned model still send an explicit chat model."""
    sse_body = b'data: {"type": "delta", "content": "Hi"}\n\ndata: [DONE]\n\n'
    model_id = "litellm:openai/gpt-4o-mini"
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/conversations/{FIXED_UUID}").mock(
            side_effect=[
                httpx.Response(200, json=_conversation_payload(FIXED_UUID, model_id=None)),
                httpx.Response(200, json=_conversation_payload(FIXED_UUID, model_id=model_id)),
            ]
        )
        models_route = r.get("/api/v1/models").mock(
            return_value=httpx.Response(200, json={"models": [{"model_id": model_id}]})
        )
        chat_route = r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse_body,
            )
        )
        result = runner.invoke(
            app,
            ["conversations", "send", "hi", "--conversation", FIXED_UUID, "--json"],
        )

    assert result.exit_code == 0, result.stdout
    assert models_route.called
    assert chat_route.called
    assert json.loads(chat_route.calls.last.request.content)["model_id"] == model_id


def test_send_existing_pinned_conversation_skips_catalog_lookup(
    runner: CliRunner, seeded: PersonaState
) -> None:
    """Existing conversations with a pinned model let the backend use that model."""
    sse_body = b'data: {"type": "delta", "content": "Hi"}\n\ndata: [DONE]\n\n'
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/conversations/{FIXED_UUID}").mock(
            return_value=httpx.Response(200, json=_conversation_payload(FIXED_UUID))
        )
        models_route = r.get("/api/v1/models").mock(
            return_value=httpx.Response(500, json={"detail": "should not be called"})
        )
        chat_route = r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse_body,
            )
        )
        result = runner.invoke(
            app,
            ["conversations", "send", "hi", "--conversation", FIXED_UUID, "--json"],
        )

    assert result.exit_code == 0, result.stdout
    assert not models_route.called
    assert "model_id" not in json.loads(chat_route.calls.last.request.content)


def test_ls_renders_json_list(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw conversations ls --json` returns the list shape."""
    payload = [
        _conversation_payload("conv-1", title="A"),
        _conversation_payload("conv-2", title="B"),
    ]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/conversations").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["conversations", "ls", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert {c["id"] for c in out} == {"conv-1", "conv-2"}


def test_ls_rejects_json_and_plain_together(runner: CliRunner, seeded: PersonaState) -> None:
    """--json and --plain are mutually exclusive."""
    result = runner.invoke(app, ["conversations", "ls", "--json", "--plain"])
    assert result.exit_code == 1


def test_show_with_messages_returns_envelope(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw conversations show <id> --with-messages --json` fetches both endpoints."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/conversations/conv-1").mock(
            return_value=httpx.Response(200, json=_conversation_payload("conv-1"))
        )
        r.get("/api/v1/conversations/conv-1/messages").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hi back"},
                ],
            )
        )
        result = runner.invoke(
            app, ["conversations", "show", "conv-1", "--with-messages", "--json"]
        )

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["conversation"]["id"] == "conv-1"
    assert len(out["messages"]) == 2


def test_rename_calls_title_endpoint(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw conversations rename` POSTs to /conversations/{id}/title."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.post("/api/v1/conversations/conv-1/title").mock(
            return_value=httpx.Response(200, json="Q2 planning")
        )
        result = runner.invoke(app, ["conversations", "rename", "conv-1", "Q2 planning", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    out = json.loads(result.stdout)
    assert out["title"] == "Q2 planning"


def test_delete_404_returns_idempotent_success(runner: CliRunner, seeded: PersonaState) -> None:
    """A delete against a missing row returns deleted=false and exit 0."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete("/api/v1/conversations/conv-gone").mock(
            return_value=httpx.Response(404, json={"detail": "Conversation not found"})
        )
        result = runner.invoke(app, ["conversations", "delete", "conv-gone", "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["deleted"] is False
    assert out["reason"] == "not_found"


def test_delete_204_returns_deleted_true(runner: CliRunner, seeded: PersonaState) -> None:
    """A successful delete returns deleted=true."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete("/api/v1/conversations/conv-1").mock(return_value=httpx.Response(204))
        result = runner.invoke(app, ["conversations", "delete", "conv-1", "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["deleted"] is True


def test_send_requires_conversation_or_new(runner: CliRunner, seeded: PersonaState) -> None:
    """Missing --conversation and --new is a local usage error (exit 1)."""
    result = runner.invoke(app, ["conversations", "send", "hi", "--json"])
    assert result.exit_code == 1


def test_export_md_renders_transcript(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw conversations export <id>` produces a markdown transcript."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/conversations/conv-1/messages").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hi back"},
                ],
            )
        )
        result = runner.invoke(app, ["conversations", "export", "conv-1"])

    assert result.exit_code == 0, result.stdout
    assert "# Conversation conv-1" in result.stdout
    assert "## user" in result.stdout
    assert "hi back" in result.stdout
