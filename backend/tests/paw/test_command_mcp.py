"""Tests for ``paw mcp`` — MCP server registry CRUD.

Mocks the backend at the HTTP layer with respx. The persona state +
cookie jar are seeded directly per ``test_command_channels.py`` to
keep the test surface narrow.
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
SERVER_ID_A = "11111111-1111-1111-1111-111111111111"
SERVER_ID_B = "22222222-2222-2222-2222-222222222222"


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in PersonaState rooted at the respx mock backend."""
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


def _server_payload(**overrides: Any) -> dict[str, Any]:
    """Build an ``McpServerResponse``-shaped row for respx mocks."""
    base: dict[str, Any] = {
        "id": SERVER_ID_A,
        "name": "notion",
        "status": "enabled",
        "config": {"command": "npx", "args": ["@notionhq/mcp"]},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# paw mcp list
# --------------------------------------------------------------------------- #


def test_mcp_list_returns_json_servers(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw mcp list --json` round-trips the bare list payload."""
    payload = [_server_payload()]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/mcp/servers").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["mcp", "list", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert isinstance(out, list)
    assert out[0]["id"] == SERVER_ID_A
    assert out[0]["name"] == "notion"


def test_mcp_list_empty_list_succeeds(runner: CliRunner, seeded: PersonaState) -> None:
    """An empty server list is a normal state, not an error."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/mcp/servers").mock(return_value=httpx.Response(200, json=[]))
        result = runner.invoke(app, ["mcp", "list", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == []


def test_mcp_list_plain_tsv_shape(runner: CliRunner, seeded: PersonaState) -> None:
    """`--plain` emits one TSV row per server (id, name, status, config keys)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/mcp/servers").mock(
            return_value=httpx.Response(200, json=[_server_payload()])
        )
        result = runner.invoke(app, ["mcp", "list", "--plain"])

    assert result.exit_code == 0, result.stdout
    columns = result.stdout.strip().split("\t")
    assert columns[0] == SERVER_ID_A
    assert columns[1] == "notion"
    assert columns[2] == "enabled"


def test_mcp_list_rejects_both_json_and_plain(runner: CliRunner, seeded: PersonaState) -> None:
    """--json + --plain is a usage error (LocalError -> exit 1)."""
    result = runner.invoke(app, ["mcp", "list", "--json", "--plain"])
    assert result.exit_code == 1


def test_mcp_list_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/mcp/servers").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["mcp", "list", "--json"])
    assert result.exit_code == 3


def test_mcp_list_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/mcp/servers").mock(return_value=httpx.Response(500, json={"detail": "boom"}))
        result = runner.invoke(app, ["mcp", "list", "--json"])
    assert result.exit_code == 5


# --------------------------------------------------------------------------- #
# paw mcp show
# --------------------------------------------------------------------------- #


def test_mcp_show_finds_row_by_id(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw mcp show <id> --json` returns the matching row from the list."""
    payload = [_server_payload(), _server_payload(id=SERVER_ID_B, name="local")]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/mcp/servers").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["mcp", "show", SERVER_ID_B, "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["id"] == SERVER_ID_B
    assert out["name"] == "local"


def test_mcp_show_missing_id_exits_1(runner: CliRunner, seeded: PersonaState) -> None:
    """A non-existent ID surfaces as a LocalError (exit 1)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/mcp/servers").mock(
            return_value=httpx.Response(200, json=[_server_payload()])
        )
        result = runner.invoke(app, ["mcp", "show", "deadbeef-0000-0000-0000-000000000000"])
    assert result.exit_code == 1


# --------------------------------------------------------------------------- #
# paw mcp create
# --------------------------------------------------------------------------- #


def test_mcp_create_posts_payload(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw mcp create` POSTs name + config + status; success exits 0."""
    config_json = '{"command":"npx","args":["@notionhq/mcp"]}'
    response_body = _server_payload()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.post("/api/v1/mcp/servers").mock(
            return_value=httpx.Response(201, json=response_body)
        )
        result = runner.invoke(
            app,
            ["mcp", "create", "--name", "notion", "--config", config_json, "--json"],
        )

    assert result.exit_code == 0, result.stdout
    assert route.called
    sent = json.loads(route.calls.last.request.content)
    assert sent["name"] == "notion"
    assert sent["status"] == "enabled"
    assert sent["config"] == {"command": "npx", "args": ["@notionhq/mcp"]}
    out = json.loads(result.stdout)
    assert out["id"] == SERVER_ID_A


def test_mcp_create_bad_config_exits_1(runner: CliRunner, seeded: PersonaState) -> None:
    """Malformed --config JSON is a local error (exit 1) before any HTTP call."""
    result = runner.invoke(app, ["mcp", "create", "--name", "n", "--config", "not-json"])
    assert result.exit_code == 1


def test_mcp_create_bad_status_exits_1(runner: CliRunner, seeded: PersonaState) -> None:
    """A status outside enabled|disabled is a local error (exit 1)."""
    result = runner.invoke(app, ["mcp", "create", "--name", "n", "--status", "bogus"])
    assert result.exit_code == 1


# --------------------------------------------------------------------------- #
# paw mcp update
# --------------------------------------------------------------------------- #


def test_mcp_update_patches_full_body(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw mcp update` fills missing fields from the current row and PATCHes."""
    current = _server_payload()
    updated = _server_payload(status="disabled")
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/mcp/servers").mock(return_value=httpx.Response(200, json=[current]))
        patch_route = r.patch(f"/api/v1/mcp/servers/{SERVER_ID_A}").mock(
            return_value=httpx.Response(200, json=updated)
        )
        result = runner.invoke(
            app, ["mcp", "update", SERVER_ID_A, "--status", "disabled", "--json"]
        )

    assert result.exit_code == 0, result.stdout
    assert patch_route.called
    sent = json.loads(patch_route.calls.last.request.content)
    assert sent["status"] == "disabled"
    # Untouched fields come from the current row so the PATCH body is valid.
    assert sent["name"] == "notion"
    assert sent["config"] == {"command": "npx", "args": ["@notionhq/mcp"]}


def test_mcp_update_requires_at_least_one_flag(runner: CliRunner, seeded: PersonaState) -> None:
    """Calling update with no flags is a local error (exit 1)."""
    result = runner.invoke(app, ["mcp", "update", SERVER_ID_A])
    assert result.exit_code == 1


# --------------------------------------------------------------------------- #
# paw mcp delete
# --------------------------------------------------------------------------- #


def test_mcp_delete_requires_yes(runner: CliRunner, seeded: PersonaState) -> None:
    """Without --yes the command is a LocalError (exit 1)."""
    result = runner.invoke(app, ["mcp", "delete", SERVER_ID_A])
    assert result.exit_code == 1


def test_mcp_delete_204_succeeds(runner: CliRunner, seeded: PersonaState) -> None:
    """A 204 deletes the row; JSON output reports deleted=true."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.delete(f"/api/v1/mcp/servers/{SERVER_ID_A}").mock(
            return_value=httpx.Response(204)
        )
        result = runner.invoke(app, ["mcp", "delete", SERVER_ID_A, "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    out = json.loads(result.stdout)
    assert out == {"deleted": True, "id": SERVER_ID_A}


def test_mcp_delete_404_is_soft_noop(runner: CliRunner, seeded: PersonaState) -> None:
    """404 on delete is treated as a soft no-op (deleted=false), exit 0."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete(f"/api/v1/mcp/servers/{SERVER_ID_A}").mock(
            return_value=httpx.Response(404, json={"detail": "MCP server not found."})
        )
        result = runner.invoke(app, ["mcp", "delete", SERVER_ID_A, "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["deleted"] is False
    assert out["reason"] == "not_found"


def test_mcp_delete_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete(f"/api/v1/mcp/servers/{SERVER_ID_A}").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        result = runner.invoke(app, ["mcp", "delete", SERVER_ID_A, "--yes"])
    assert result.exit_code == 5
