"""Integration tests for paw login + auth status + logout against a respx-mocked backend."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
LOGIN_EXIT_CODE_LOCAL_ERROR = 1
AUTH_STATUS_EXIT_CODE_UNAUTH = 3


def _admin_workspace() -> dict[str, Any]:
    """Minimal WorkspaceRead-shaped payload accepted by the login flow."""
    return {
        "id": "ws-1",
        "name": "Main",
        "slug": "main",
        "path": "/tmp/ws",
        "is_default": True,
        "created_at": "2026-05-27T00:00:00Z",
    }


@pytest.fixture
def mock_backend() -> Iterator[str]:
    """Stand up a respx mock that mirrors the real dev-admin login surface."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.post("/auth/dev-login").mock(
            return_value=httpx.Response(
                204,
                headers={
                    "set-cookie": (
                        "session_token=tok123; Path=/; HttpOnly; "
                        "Expires=Wed, 27-May-2099 12:00:00 GMT"
                    ),
                },
            )
        )
        r.get("/api/v1/users/me").mock(
            return_value=httpx.Response(200, json={"id": "u1", "email": "admin@example.com"})
        )
        # First /api/v1/workspaces call returns empty; the login flow seeds via
        # personalization and re-fetches. respx.get matches every GET, so the
        # second call returns the workspace too — flip via side_effect.
        workspaces_responses = [
            httpx.Response(200, json=[]),
            httpx.Response(200, json=[_admin_workspace()]),
        ]
        r.get("/api/v1/workspaces").mock(side_effect=workspaces_responses)
        r.put("/api/v1/personalization").mock(return_value=httpx.Response(200, json={}))
        r.post("/auth/jwt/logout").mock(return_value=httpx.Response(204))
        yield MOCK_BACKEND


def test_login_dev_admin_stores_state_and_cookies(runner, mock_backend):
    """Happy path: login persists state.json with user + workspace IDs."""
    result = runner.invoke(app, ["login", "--dev-admin", "--api", mock_backend, "--json"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["user_email"] == "admin@example.com"
    assert out["default_workspace_id"] == "ws-1"


def test_login_is_idempotent_when_workspace_already_exists(runner):
    """If the workspace already exists, the login flow must not re-seed."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.post("/auth/dev-login").mock(
            return_value=httpx.Response(
                204,
                headers={"set-cookie": "session_token=tok456; Path=/; HttpOnly"},
            )
        )
        r.get("/api/v1/users/me").mock(
            return_value=httpx.Response(200, json={"id": "u1", "email": "admin@example.com"})
        )
        existing_ws = {
            "id": "ws-existing",
            "name": "Main",
            "slug": "main",
            "path": "/tmp/ws",
            "is_default": True,
            "created_at": "2026-05-27T00:00:00Z",
        }
        r.get("/api/v1/workspaces").mock(return_value=httpx.Response(200, json=[existing_ws]))
        seed = r.put("/api/v1/personalization").mock(return_value=httpx.Response(200, json={}))
        result = runner.invoke(app, ["login", "--dev-admin", "--api", MOCK_BACKEND, "--json"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["default_workspace_id"] == "ws-existing"
    assert not seed.called, "personalization PUT must not fire when workspace exists"


def test_login_requires_credentials(runner):
    """Missing --dev-admin and missing email+password is a usage error (exit 1)."""
    result = runner.invoke(app, ["login", "--json"])
    assert result.exit_code == LOGIN_EXIT_CODE_LOCAL_ERROR


def test_auth_status_unauthenticated_exits_3(runner):
    """No state file -> authenticated=false, exit code 3."""
    result = runner.invoke(app, ["auth", "status", "--json"])
    assert result.exit_code == AUTH_STATUS_EXIT_CODE_UNAUTH
    out = json.loads(result.stdout)
    assert out["authenticated"] is False


def test_auth_status_authenticated_after_login(runner, mock_backend):
    """After login, /users/me confirms identity and exit code is 0."""
    runner.invoke(app, ["login", "--dev-admin", "--api", mock_backend, "--json"])
    result = runner.invoke(app, ["auth", "status", "--json"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["authenticated"] is True
    assert out["user_email"] == "admin@example.com"


def test_logout_deletes_state_and_cookies(runner, mock_backend):
    """Logout wipes the local files; subsequent auth status returns unauthenticated."""
    runner.invoke(app, ["login", "--dev-admin", "--api", mock_backend, "--json"])
    result = runner.invoke(app, ["logout", "--yes", "--json"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["deleted"] is True
    status_result = runner.invoke(app, ["auth", "status", "--json"])
    assert status_result.exit_code == AUTH_STATUS_EXIT_CODE_UNAUTH
