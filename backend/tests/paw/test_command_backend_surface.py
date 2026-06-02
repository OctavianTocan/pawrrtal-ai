"""Tests for paw commands covering backend surfaces beyond chat."""

from __future__ import annotations

import json
from typing import Any

import httpx
import respx
from typer.testing import CliRunner

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
WORKSPACE_ID = "11111111-2222-3333-4444-555555555555"
PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _seed_persona() -> PersonaState:
    """Persist a logged-in PersonaState carrying a default workspace."""
    state = PersonaState(
        profile="default",
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="admin@example.com",
        default_workspace_id=WORKSPACE_ID,
    )
    state.save()
    jar = load_cookies(cookies_path("default"))
    save_cookies(jar, cookies_path("default"))
    return state


def _project_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": PROJECT_ID,
        "user_id": "00000000-0000-0000-0000-000000000001",
        "name": "Launch",
        "created_at": "2026-06-02T00:00:00Z",
        "updated_at": "2026-06-02T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_projects_create_posts_name(runner: CliRunner) -> None:
    _seed_persona()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.post("/api/v1/projects").mock(
            return_value=httpx.Response(201, json=_project_payload())
        )
        result = runner.invoke(app, ["projects", "create", "Launch", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(route.calls[0].request.content) == {"name": "Launch"}
    assert json.loads(result.stdout)["id"] == PROJECT_ID


def test_projects_delete_404_is_idempotent(runner: CliRunner) -> None:
    _seed_persona()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete(f"/api/v1/projects/{PROJECT_ID}").mock(
            return_value=httpx.Response(404, json={"detail": "Project not found"})
        )
        result = runner.invoke(app, ["projects", "delete", PROJECT_ID, "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["deleted"] is False


def test_profile_set_merges_existing_profile(runner: CliRunner) -> None:
    _seed_persona()
    existing = {"name": "Octavian", "role": "founder", "goals": ["ship"]}
    saved = {**existing, "role": "operator", "goals": ["polish"]}
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/personalization").mock(return_value=httpx.Response(200, json=existing))
        route = r.put("/api/v1/personalization").mock(return_value=httpx.Response(200, json=saved))
        result = runner.invoke(
            app,
            ["profile", "set", "--role", "operator", "--goal", "polish", "--json"],
        )

    assert result.exit_code == 0, result.stdout
    assert json.loads(route.calls[0].request.content) == saved
    assert json.loads(result.stdout)["role"] == "operator"


def test_appearance_set_merges_nested_fields(runner: CliRunner) -> None:
    _seed_persona()
    existing = {"light": {}, "dark": {}, "fonts": {"sans": "Google Sans"}, "options": {}}
    response = {
        "light": {"accent": "#7c5cff"},
        "dark": {},
        "fonts": {"sans": "Google Sans"},
        "options": {"theme_mode": "dark", "pointer_cursors": True},
    }
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/appearance").mock(return_value=httpx.Response(200, json=existing))
        route = r.put("/api/v1/appearance").mock(return_value=httpx.Response(200, json=response))
        result = runner.invoke(
            app,
            [
                "appearance",
                "set",
                "--accent",
                "#7c5cff",
                "--theme-mode",
                "dark",
                "--pointer-cursors",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    body = json.loads(route.calls[0].request.content)
    assert body["light"]["accent"] == "#7c5cff"
    assert body["options"]["theme_mode"] == "dark"
    assert body["options"]["pointer_cursors"] is True


def test_appearance_reset_deletes_settings(runner: CliRunner) -> None:
    _seed_persona()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.delete("/api/v1/appearance").mock(return_value=httpx.Response(204))
        result = runner.invoke(app, ["appearance", "reset", "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    assert json.loads(result.stdout) == {"reset": True}


def test_completions_autocomplete_posts_text(runner: CliRunner) -> None:
    _seed_persona()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.post("/api/v1/completions/autocomplete").mock(
            return_value=httpx.Response(200, json={"suggestion": " tomorrow"})
        )
        result = runner.invoke(app, ["completions", "autocomplete", "let's ship", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(route.calls[0].request.content) == {"text": "let's ship"}
    assert json.loads(result.stdout)["suggestion"] == " tomorrow"


def test_heartbeat_sync_returns_json(runner: CliRunner) -> None:
    _seed_persona()
    payload = {
        "workspace_id": WORKSPACE_ID,
        "conversation_id": "22222222-3333-4444-5555-666666666666",
        "jobs_created": 2,
        "jobs_removed": 1,
        "telegram_linked": True,
    }
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.post("/api/v1/heartbeat/sync").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["heartbeat", "sync", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["jobs_created"] == 2


def test_workspace_status_uses_onboarding_endpoint(runner: CliRunner) -> None:
    _seed_persona()
    payload = {
        "has_workspace_ready": True,
        "workspace": {"id": WORKSPACE_ID, "name": "main"},
    }
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/workspaces/onboarding-status").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(app, ["workspace", "status", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["has_workspace_ready"] is True


def test_workspace_skills_lists_default_workspace_skills(runner: CliRunner) -> None:
    _seed_persona()
    payload = [
        {
            "name": "pawrrtal-taste",
            "trigger": "polish",
            "summary": "Clean modern Pawrrtal UX rules.",
            "has_skill_md": True,
        }
    ]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/workspaces/{WORKSPACE_ID}/skills").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(app, ["workspace", "skills", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)[0]["name"] == "pawrrtal-taste"


def test_audit_summary_fetches_dashboard_aggregate(runner: CliRunner) -> None:
    _seed_persona()
    payload = {"total_events": 3, "by_event_type": {"chat.turn": 2}, "by_risk_level": {"low": 3}}
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.get("/api/v1/audit/summary").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["audit", "summary", "--hours", "12", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.calls[0].request.url.params["hours"] == "12"
    assert json.loads(result.stdout)["total_events"] == 3
