"""Tests for ``paw workspaces`` / ``paw workspace env|files`` commands.

Mocks the backend at the HTTP layer with respx. The persona state +
cookie jar are seeded directly per :file:`test_command_conversations.py`
to keep the test surface narrow.
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
WORKSPACE_ID = "11111111-2222-3333-4444-555555555555"
OTHER_WORKSPACE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _seed_persona(
    profile: str = "default", *, default_workspace_id: str = WORKSPACE_ID
) -> PersonaState:
    """Persist a logged-in PersonaState carrying a default workspace."""
    state = PersonaState(
        profile=profile,
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="admin@example.com",
        default_workspace_id=default_workspace_id,
    )
    state.save()
    jar = load_cookies(cookies_path(profile))
    save_cookies(jar, cookies_path(profile))
    return state


@pytest.fixture
def seeded() -> PersonaState:
    return _seed_persona()


def _workspace_payload(workspace_id: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": workspace_id,
        "name": "main",
        "slug": "main",
        "path": f"/workspaces/{workspace_id}",
        "is_default": True,
        "created_at": "2026-05-27T00:00:00Z",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# workspaces ls / show / use / create / rename / delete
# --------------------------------------------------------------------------- #


def test_workspaces_ls_returns_json_list(runner: CliRunner, seeded: PersonaState) -> None:
    payload = [
        _workspace_payload(WORKSPACE_ID, name="A"),
        _workspace_payload(OTHER_WORKSPACE_ID, name="B", is_default=False),
    ]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/workspaces").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["workspaces", "ls", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert {w["id"] for w in out} == {WORKSPACE_ID, OTHER_WORKSPACE_ID}


def test_workspaces_show_uses_default_id_when_no_override(
    runner: CliRunner, seeded: PersonaState
) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/workspaces").mock(
            return_value=httpx.Response(200, json=[_workspace_payload(WORKSPACE_ID, name="A")])
        )
        result = runner.invoke(app, ["workspaces", "show", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["id"] == WORKSPACE_ID


def test_workspaces_show_404_when_id_unknown(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/workspaces").mock(return_value=httpx.Response(200, json=[]))
        result = runner.invoke(app, ["workspaces", "show", "--workspace", "missing"])

    # LocalError when workspace not found -> exit 1.
    assert result.exit_code == 1


def test_workspaces_use_persists_default(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw workspaces use ID` persists state.default_workspace_id."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/workspaces").mock(
            return_value=httpx.Response(
                200, json=[_workspace_payload(OTHER_WORKSPACE_ID, name="B", is_default=False)]
            )
        )
        result = runner.invoke(app, ["workspaces", "use", OTHER_WORKSPACE_ID, "--json"])

    assert result.exit_code == 0, result.stdout
    reloaded = PersonaState.load("default")
    assert reloaded.default_workspace_id == OTHER_WORKSPACE_ID
    assert reloaded.default_workspace_path == f"/workspaces/{OTHER_WORKSPACE_ID}"


def test_workspaces_create_posts_with_path(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.post("/api/v1/workspaces").mock(
            return_value=httpx.Response(
                201, json=_workspace_payload(OTHER_WORKSPACE_ID, name="exploration")
            )
        )
        result = runner.invoke(
            app,
            [
                "workspaces",
                "create",
                "exploration",
                "--path",
                "/workspaces/exploration",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    assert route.called
    body = json.loads(route.calls[0].request.content)
    assert body["name"] == "exploration"
    assert body["path"] == "/workspaces/exploration"


def test_workspaces_rename_patches(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.patch(f"/api/v1/workspaces/{WORKSPACE_ID}").mock(
            return_value=httpx.Response(200, json=_workspace_payload(WORKSPACE_ID, name="research"))
        )
        result = runner.invoke(app, ["workspaces", "rename", WORKSPACE_ID, "research", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    body = json.loads(route.calls[0].request.content)
    assert body == {"name": "research"}


def test_workspaces_delete_404_returns_idempotent_success(
    runner: CliRunner, seeded: PersonaState
) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete(f"/api/v1/workspaces/{WORKSPACE_ID}").mock(
            return_value=httpx.Response(404, json={"detail": "Workspace not found"})
        )
        result = runner.invoke(app, ["workspaces", "delete", WORKSPACE_ID, "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["deleted"] is False


def test_workspaces_delete_409_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """A 409 (cannot delete last/default workspace) surfaces as ApiError exit 5."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete(f"/api/v1/workspaces/{WORKSPACE_ID}").mock(
            return_value=httpx.Response(409, json={"detail": "Cannot delete the only workspace"})
        )
        result = runner.invoke(app, ["workspaces", "delete", WORKSPACE_ID, "--yes"])

    assert result.exit_code == 5


# --------------------------------------------------------------------------- #
# workspace env get / set / unset
# --------------------------------------------------------------------------- #


def test_env_get_full_dict(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/workspaces/{WORKSPACE_ID}/env").mock(
            return_value=httpx.Response(
                200,
                json={"vars": {"GEMINI_API_KEY": "sk-abc", "OPENAI_API_KEY": ""}},
            )
        )
        result = runner.invoke(app, ["workspace", "env", "get", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["GEMINI_API_KEY"] == "sk-abc"


def test_env_get_single_key(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/workspaces/{WORKSPACE_ID}/env").mock(
            return_value=httpx.Response(200, json={"vars": {"GEMINI_API_KEY": "sk-abc"}})
        )
        result = runner.invoke(app, ["workspace", "env", "get", "GEMINI_API_KEY"])

    assert result.exit_code == 0, result.stdout
    assert "sk-abc" in result.stdout


def test_env_set_puts_delta(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.put(f"/api/v1/workspaces/{WORKSPACE_ID}/env").mock(
            return_value=httpx.Response(200, json={"vars": {"GEMINI_API_KEY": "sk-new"}})
        )
        result = runner.invoke(
            app,
            ["workspace", "env", "set", "GEMINI_API_KEY=sk-new", "--json"],
        )

    assert result.exit_code == 0, result.stdout
    assert route.called
    body = json.loads(route.calls[0].request.content)
    assert body == {"vars": {"GEMINI_API_KEY": "sk-new"}}


def test_env_set_rejects_bad_pair(runner: CliRunner, seeded: PersonaState) -> None:
    result = runner.invoke(app, ["workspace", "env", "set", "no-equals-sign"])
    assert result.exit_code == 1


def test_env_unset_deletes_each_key(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete(f"/api/v1/workspaces/{WORKSPACE_ID}/env/GEMINI_API_KEY").mock(
            return_value=httpx.Response(204)
        )
        r.delete(f"/api/v1/workspaces/{WORKSPACE_ID}/env/EXA_API_KEY").mock(
            return_value=httpx.Response(404, json={"detail": "Unknown workspace env key"})
        )
        result = runner.invoke(
            app,
            [
                "workspace",
                "env",
                "unset",
                "GEMINI_API_KEY",
                "EXA_API_KEY",
                "--yes",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out[0] == {"key": "GEMINI_API_KEY", "deleted": True}
    assert out[1]["deleted"] is False


# --------------------------------------------------------------------------- #
# workspace files ls / cat / write / rm
# --------------------------------------------------------------------------- #


def test_files_ls_filters_by_prefix(runner: CliRunner, seeded: PersonaState) -> None:
    nodes = [
        {"name": "memory", "path": "memory", "is_dir": True, "size": None},
        {"name": "a.md", "path": "memory/a.md", "is_dir": False, "size": 12},
        {"name": "b.md", "path": "notes/b.md", "is_dir": False, "size": 24},
    ]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/workspaces/{WORKSPACE_ID}/tree").mock(
            return_value=httpx.Response(200, json={"workspace_id": WORKSPACE_ID, "nodes": nodes})
        )
        result = runner.invoke(app, ["workspace", "files", "ls", "memory", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert {n["path"] for n in out} == {"memory", "memory/a.md"}


def test_files_cat_prints_raw_content(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/workspaces/{WORKSPACE_ID}/files/memory/a.md").mock(
            return_value=httpx.Response(200, json={"path": "memory/a.md", "content": "hello world"})
        )
        result = runner.invoke(app, ["workspace", "files", "cat", "memory/a.md"])

    assert result.exit_code == 0, result.stdout
    assert "hello world" in result.stdout


def test_files_write_from_stdin(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.put(f"/api/v1/workspaces/{WORKSPACE_ID}/files/notes/todo.md").mock(
            return_value=httpx.Response(
                200, json={"path": "notes/todo.md", "content": "milk\neggs\n"}
            )
        )
        result = runner.invoke(
            app,
            ["workspace", "files", "write", "notes/todo.md", "--stdin"],
            input="milk\neggs\n",
        )

    assert result.exit_code == 0, result.stdout
    assert route.called
    body = json.loads(route.calls[0].request.content)
    assert body == {"content": "milk\neggs\n"}


def test_files_write_rejects_both_stdin_and_data(runner: CliRunner, seeded: PersonaState) -> None:
    result = runner.invoke(
        app,
        ["workspace", "files", "write", "x.md", "--stdin", "-d", "hello"],
        input="ignored\n",
    )
    assert result.exit_code == 1


def test_files_rm_404_returns_idempotent_success(runner: CliRunner, seeded: PersonaState) -> None:
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete(f"/api/v1/workspaces/{WORKSPACE_ID}/files/gone.md").mock(
            return_value=httpx.Response(404, json={"detail": "File not found"})
        )
        result = runner.invoke(app, ["workspace", "files", "rm", "gone.md", "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["deleted"] is False


def test_resolve_workspace_requires_default_or_override(runner: CliRunner) -> None:
    """An unset default_workspace_id without --workspace raises LocalError."""
    _seed_persona(default_workspace_id="")
    state = PersonaState.load("default")
    state.default_workspace_id = None
    state.save()

    result = runner.invoke(app, ["workspace", "env", "get", "--json"])
    assert result.exit_code == 1
