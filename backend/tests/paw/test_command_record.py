"""Tests for ``paw record`` — fixture capture wrapper."""

from __future__ import annotations

import json

import httpx
import respx

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"


def _seed_persona(profile: str = "default") -> None:
    """Persist a logged-in PersonaState so wrapped commands have a session."""
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


def test_record_writes_jsonl_for_wrapped_auth_status(runner, tmp_path):
    """`paw record --to <path> auth status --json` captures a single request row."""
    _seed_persona()
    fixture = tmp_path / "auth_status.jsonl"
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=True) as r:
        r.get("/api/v1/users/me").mock(
            return_value=httpx.Response(200, json={"id": "u1", "email": "admin@example.com"})
        )
        result = runner.invoke(app, ["record", "--to", str(fixture), "auth", "status", "--json"])
    assert result.exit_code == 0, result.stdout
    assert fixture.exists(), "record must produce the fixture file"
    rows = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["method"] == "GET"
    assert row["url"].endswith("/api/v1/users/me")
    assert row["status"] == 200
    assert row["is_stream"] is False
    body = json.loads(str(row["response_body"]))
    assert body["email"] == "admin@example.com"


def test_record_requires_wrapped_command(runner, tmp_path):
    """Bare `paw record --to ...` with no wrapped command is a LocalError (exit 1)."""
    fixture = tmp_path / "empty.jsonl"
    result = runner.invoke(app, ["record", "--to", str(fixture)])
    assert result.exit_code == 1
