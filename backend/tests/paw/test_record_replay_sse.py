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
DEFAULT_MODEL = "litellm:openai/gpt-4o-mini"


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
        "provider_session_id": None,
    }
    base.update(overrides)
    return base


def _models_payload() -> dict[str, Any]:
    """Minimal model catalog payload used by CLI quick-start defaults."""
    return {"models": [{"model_id": DEFAULT_MODEL}]}


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


@pytest.mark.anyio
async def test_record_sse_frame_writes_method_field(tmp_path: Path) -> None:
    """Recorded SSE rows must carry the HTTP method that produced them.

    Without ``method`` on the row, ``paw replay`` defaulted every SSE
    body to POST and silently ignored GET-based streams. The recorder
    now stamps each frame with its verb so replay's ``(method, url)``
    keying matches what the live consumer saw.
    """
    _seed_persona("test-method")
    state = PersonaState(
        profile="test-method",
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="x@x.com",
    )
    state.save()
    fixture = tmp_path / "frame.jsonl"
    from app.cli.paw.http import PawClient

    async with PawClient(state, record_path=fixture) as client:
        client.record_sse_frame("POST", "http://test-backend/api/v1/chat/", b"data: hi\n")
    rows = [json.loads(line) for line in fixture.read_text().splitlines() if line]
    assert len(rows) == 1
    assert rows[0]["method"] == "POST"
    assert rows[0]["url"] == "http://test-backend/api/v1/chat/"
    assert rows[0]["type"] == "sse"
    assert "frame_b64" in rows[0]


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
        r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_models_payload()))
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

    # First, record an existing unpinned conversation into the fixture. The
    # request sequence must match replay: pre-send conversation lookup, model
    # lookup, streaming chat POST, then post-send conversation fetch.
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_models_payload()))
        r.get(f"/api/v1/conversations/{stable_uuid}").mock(
            side_effect=[
                httpx.Response(200, json=_conversation_payload(stable_uuid, model_id=None)),
                httpx.Response(
                    200,
                    json=_conversation_payload(
                        stable_uuid,
                        model_id=DEFAULT_MODEL,
                        provider_session_id="thread-abc",
                    ),
                ),
            ]
        )
        r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=SSE_BODY,
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
                "--conversation",
                stable_uuid,
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
    assert out["provider_session_id"] == "thread-abc"


SECOND_SSE_BODY = (
    b'data: {"type": "delta", "content": "Second"}\n\n'
    b'data: {"type": "delta", "content": " turn"}\n\n'
    b'data: {"type": "usage", "input_tokens": 7, "output_tokens": 3}\n\n'
    b"data: [DONE]\n\n"
)


def test_replay_keeps_per_turn_sse_bodies_distinct(
    runner: CliRunner,
    tmp_path: Path,
    stable_uuid: str,
) -> None:
    """Two stream rows against the same URL must replay as two distinct bodies.

    Regression: the original ``_build_sse_bodies`` keyed by URL alone and
    emitted exactly one body per URL no matter how many ``is_stream=True``
    HTTP envelopes were captured. The first POST consumed the fused
    concatenation of every recorded chat turn; subsequent POSTs got an
    empty body which the framer silently decoded as zero events. This
    test asserts each invocation now sees its original frames.
    """
    del runner, stable_uuid  # not used; helpers don't require them.
    _seed_persona()
    fixture = tmp_path / "two_turns.jsonl"

    chat_url = f"{MOCK_BACKEND}/api/v1/chat/"
    rows: list[dict[str, Any]] = []
    rows.append(
        {
            "type": "http",
            "method": "POST",
            "url": chat_url,
            "status": 200,
            "response_headers": {"content-type": "text/event-stream"},
            "response_body": None,
            "is_stream": True,
        }
    )
    for frame in SSE_BODY.split(b"\n\n"):
        if not frame.strip():
            continue
        rows.append(
            {
                "type": "sse",
                "url": chat_url,
                "frame_b64": base64.b64encode(frame).decode("ascii"),
            }
        )
    rows.append(
        {
            "type": "http",
            "method": "POST",
            "url": chat_url,
            "status": 200,
            "response_headers": {"content-type": "text/event-stream"},
            "response_body": None,
            "is_stream": True,
        }
    )
    for frame in SECOND_SSE_BODY.split(b"\n\n"):
        if not frame.strip():
            continue
        rows.append(
            {
                "type": "sse",
                "url": chat_url,
                "frame_b64": base64.b64encode(frame).decode("ascii"),
            }
        )
    fixture.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    from app.cli.paw.commands.replay import _build_sse_bodies, _load_rows

    parsed_rows = _load_rows(fixture)
    bodies = _build_sse_bodies(parsed_rows)
    key = ("POST", chat_url)
    assert len(bodies[key]) == 2, bodies
    # First body matches turn 1's frames (in particular contains "Hi" not
    # "Second"); second body matches turn 2's. Without the fix, the
    # second body would be empty.
    assert b'"content": "Hi"' in bodies[key][0]
    assert b'"content": " there"' in bodies[key][0]
    assert b"Second" not in bodies[key][0]
    assert b'"content": "Second"' in bodies[key][1]
    assert b'"content": " turn"' in bodies[key][1]
    assert b'"content": "Hi"' not in bodies[key][1]
