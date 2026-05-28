"""End-to-end record→replay roundtrip for the SSE chat stream.

Captures `paw conversations send --new` against an SSE-emitting upstream,
asserts the JSONL fixture contains one `type=sse` row per `data:` frame
(including the `[DONE]` sentinel), then replays the fixture and verifies
the consumer reconstructs the same events without touching the upstream.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
NEW_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
EXPECTED_FRAME_COUNT = 4


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
        "codex_thread_id": None,
    }
    base.update(overrides)
    return base


SSE_BODY = (
    b'data: {"type": "delta", "content": "Hi"}\n\n'
    b'data: {"type": "delta", "content": " there"}\n\n'
    b'data: {"type": "usage", "input_tokens": 5, "output_tokens": 2}\n\n'
    b"data: [DONE]\n\n"
)


@pytest.fixture
def stable_uuid(monkeypatch: pytest.MonkeyPatch) -> str:
    """Pin ``ids.new_conversation_id`` to a deterministic value."""
    monkeypatch.setattr("app.cli.paw.ids.new_conversation_id", lambda: NEW_UUID)
    return NEW_UUID


def test_record_captures_one_jsonl_row_per_sse_frame(
    runner: CliRunner,
    tmp_path: Path,
    stable_uuid: str,
) -> None:
    """`paw record` writes one ``type=sse`` row per ``data:`` frame.

    The HTTP envelope for the streaming POST stays in the fixture too
    (``is_stream=true``, empty body) so replay can mount the right
    method+url with the right status.
    """
    _seed_persona()
    fixture = tmp_path / "chat_stream.jsonl"
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.post(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conversation_payload(stable_uuid))
        )
        r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=SSE_BODY,
            )
        )
        r.get(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conversation_payload(stable_uuid))
        )
        result = runner.invoke(
            app,
            [
                "record",
                "--to",
                str(fixture),
                "conversations",
                "send",
                "hi",
                "--new",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout

    rows = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]
    sse_rows = [row for row in rows if row.get("type") == "sse"]
    chat_url = f"{MOCK_BACKEND}/api/v1/chat/"
    assert len(sse_rows) == EXPECTED_FRAME_COUNT, sse_rows
    for sse_row in sse_rows:
        assert sse_row["url"] == chat_url

    # Decoded frames must round-trip back to the original wire payloads.
    decoded = [base64.b64decode(row["frame_b64"]) for row in sse_rows]
    assert b'data: {"type": "delta", "content": "Hi"}' in decoded[0]
    assert decoded[-1].strip() == b"data: [DONE]"

    # The envelope for the streaming POST is still recorded — replay needs
    # the (method, url, status, headers) tuple to mount the route.
    chat_envelope = next(
        row
        for row in rows
        if row.get("type") not in {"sse", "sse_done"}
        and row.get("url") == chat_url
        and row.get("is_stream") is True
    )
    assert chat_envelope["status"] == 200
    assert chat_envelope["response_body"] is None


def test_replay_reconstructs_sse_stream_from_fixture(
    runner: CliRunner,
    tmp_path: Path,
    stable_uuid: str,
) -> None:
    """A fixture captured by `paw record` replays back through `paw conversations send`.

    Asserts the SSE consumer reassembles the same events (delta count,
    final text, usage frame) without any upstream being available — respx
    has ``assert_all_mocked=True`` by default, so any unmocked request
    would fail the test loudly.
    """
    _seed_persona()
    fixture = tmp_path / "chat_stream.jsonl"

    # First, record into the fixture.
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.post(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conversation_payload(stable_uuid))
        )
        r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=SSE_BODY,
            )
        )
        r.get(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(
                200,
                json=_conversation_payload(stable_uuid, codex_thread_id="thread-abc"),
            )
        )
        record_result = runner.invoke(
            app,
            [
                "record",
                "--to",
                str(fixture),
                "conversations",
                "send",
                "hi",
                "--new",
                "--json",
            ],
        )
    assert record_result.exit_code == 0, record_result.stdout

    # Then replay it. ``paw replay`` builds its own respx mock from the
    # JSONL — no upstream involvement.
    replay_result = runner.invoke(
        app,
        [
            "replay",
            "--from",
            str(fixture),
            "conversations",
            "send",
            "hi",
            "--conversation",
            stable_uuid,
            "--json",
        ],
    )
    assert replay_result.exit_code == 0, replay_result.stdout
    out = json.loads(replay_result.stdout)
    assert out["conversation_id"] == stable_uuid
    assert out["final_text"] == "Hi there"
    assert out["events"]["delta"] == 2
    assert out["events"]["usage"] == 1
    assert out["codex_thread_id"] == "thread-abc"
