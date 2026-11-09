"""Tests for ``paw replay`` — replay a recorded JSONL fixture in-process."""

from __future__ import annotations

import json
from pathlib import Path

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
LOCAL_ERROR_EXIT_CODE = 1


def _seed_persona(profile: str = "default") -> None:
    """Persist a logged-in PersonaState pointed at the recorded backend host."""
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


def _write_fixture(path: Path, rows: list[dict[str, object]]) -> None:
    """Serialize rows as JSONL at ``path``."""
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row))
            f.write("\n")


def test_replay_serves_recorded_response(runner, tmp_path):
    """A fixture with one /users/me row replays into a successful auth status."""
    _seed_persona()
    fixture = tmp_path / "replay.jsonl"
    _write_fixture(
        fixture,
        [
            {
                "method": "GET",
                "url": f"{MOCK_BACKEND}/api/v1/users/me",
                "request_headers": {},
                "request_body": None,
                "status": 200,
                "response_headers": {"content-type": "application/json"},
                "response_body": json.dumps({"id": "u1", "email": "replayed@example.com"}),
                "response_body_bytes_b64": None,
                "is_stream": False,
                "duration_ms": 5,
            }
        ],
    )
    result = runner.invoke(app, ["replay", "--from", str(fixture), "auth", "status", "--json"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["authenticated"] is True
    assert out["user_email"] == "replayed@example.com"


def test_replay_missing_fixture_exits_local_error(runner, tmp_path):
    """A missing fixture path is a LocalError (exit 1)."""
    result = runner.invoke(
        app, ["replay", "--from", str(tmp_path / "nope.jsonl"), "auth", "status"]
    )
    assert result.exit_code == LOCAL_ERROR_EXIT_CODE


def test_replay_skips_malformed_jsonl_rows(runner, tmp_path):
    """A fixture with a truncated/malformed row replays the good rows.

    Simulates a SIGKILL mid-write that leaves one row half-flushed: the
    decoder must skip the bad line with a warning rather than crashing
    the replay run.
    """
    _seed_persona()
    fixture = tmp_path / "replay-with-garbage.jsonl"
    good_row = {
        "method": "GET",
        "url": f"{MOCK_BACKEND}/api/v1/users/me",
        "request_headers": {},
        "request_body": None,
        "status": 200,
        "response_headers": {"content-type": "application/json"},
        "response_body": json.dumps({"id": "u1", "email": "replayed@example.com"}),
        "response_body_bytes_b64": None,
        "is_stream": False,
        "duration_ms": 5,
    }
    with fixture.open("w", encoding="utf-8") as f:
        f.write(json.dumps(good_row) + "\n")
        # Truncated row — looks like SIGKILL interrupted the write
        # between the JSON payload and the trailing newline.
        f.write('{"method": "GET", "url": "trunc')
    result = runner.invoke(app, ["replay", "--from", str(fixture), "auth", "status", "--json"])
    assert result.exit_code == 0, result.stdout
