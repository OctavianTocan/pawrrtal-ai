"""HTTP-level tests for the /api/v1/workspaces/{workspace_id}/env router.

Exercises the actual endpoints (not the helpers in keys.py — those have
their own unit tests in test_keys.py). Covers:

  * GET returns every overridable key with empty defaults for unset workspaces.
  * GET reflects what was previously persisted via PUT.
  * PUT happy path round-trips through encryption.
  * PUT rejects an unknown key with 400 (allowlist enforcement).
  * PUT rejects newline injection with 422 (validator-level guard).
  * PUT preserves keys not mentioned in the payload (PATCH semantics).
  * PUT with empty-string strips the key on disk (works as "clear" path).
  * DELETE removes a single key idempotently.
  * DELETE on an unknown key returns 404.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure import keys
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User
from app.infrastructure.keys import OVERRIDABLE_KEYS
from app.models import Workspace

PLUGIN_TOKEN_KEY = "CUSTOM_PLUGIN_TOKEN"


@pytest.fixture
def isolate_workspace_base(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point keys.py at a per-test temp directory, isolating the filesystem.

    Same pattern used by test_keys.py — re-pointed live so individual
    `_workspace_env_path` calls pick it up without re-importing.
    """
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    return tmp_path


def _write_workspace_settings_plugin(workspace_root: Path) -> None:
    """Write a workspace plugin that declares one overridable env key."""
    plugin_dir = workspace_root / ".agent" / "plugins" / "custom_env"
    plugin_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "custom_env",
        "name": "Custom Env",
        "version": "1.0.0",
        "description": "Workspace plugin used to test dynamic env settings.",
        "capabilities": [
            {
                "type": "settings",
                "id": "custom_env_settings",
                "title": "Custom Env Settings",
                "description": "Settings metadata for a custom workspace plugin.",
                "env": [
                    {
                        "name": PLUGIN_TOKEN_KEY,
                        "label": "Custom Plugin Token",
                        "description": "Token configured per workspace for this plugin.",
                        "help_url": "https://example.com/plugin-token",
                        "required": True,
                        "scope": "workspace",
                        "overridable": True,
                        "secret": True,
                    }
                ],
            }
        ],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.anyio
async def test_get_returns_all_keys_empty_for_new_user(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """A workspace that has never saved overrides sees every key with `""`."""
    response = await client.get(f"/api/v1/workspaces/{seeded_default_workspace.id}/env")
    assert response.status_code == 200
    body = response.json()
    # Derive expected keys from the canonical OVERRIDABLE_KEYS constant
    # rather than hardcoding them. This prevents the test from breaking
    # when new keys are added, and removes sensitivity to stale .pyc
    # files on the self-hosted runner.
    assert set(body["vars"].keys()) == set(OVERRIDABLE_KEYS)
    assert {row["key"] for row in body["keys"]} == set(OVERRIDABLE_KEYS)
    assert all(v == "" for v in body["vars"].values())


@pytest.mark.anyio
async def test_get_includes_workspace_plugin_env_keys(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """Plugin settings contribute env keys to the owning workspace."""
    _write_workspace_settings_plugin(Path(seeded_default_workspace.path))

    response = await client.get(f"/api/v1/workspaces/{seeded_default_workspace.id}/env")

    assert response.status_code == 200
    body = response.json()
    assert body["vars"][PLUGIN_TOKEN_KEY] == ""
    metadata = next(row for row in body["keys"] if row["key"] == PLUGIN_TOKEN_KEY)
    assert metadata == {
        "key": PLUGIN_TOKEN_KEY,
        "label": "Custom Plugin Token",
        "description": "Token configured per workspace for this plugin.",
        "secret": True,
        "required": True,
        "source": "plugin",
        "help_url": "https://example.com/plugin-token",
    }


@pytest.mark.anyio
async def test_plugin_env_keys_do_not_leak_between_workspaces(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
    test_user: User,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """A workspace-local plugin key is not accepted in another workspace."""
    _write_workspace_settings_plugin(Path(seeded_default_workspace.path))
    other_root = tmp_path / "other-workspace"
    other_root.mkdir()
    other = Workspace(
        id=uuid4(),
        user_id=test_user.id,
        name="Other",
        slug="other",
        path=str(other_root),
        is_default=False,
    )
    db_session.add(other)
    await db_session.commit()

    response = await client.get(f"/api/v1/workspaces/{other.id}/env")

    assert response.status_code == 200
    assert PLUGIN_TOKEN_KEY not in response.json()["vars"]
    assert PLUGIN_TOKEN_KEY not in {row["key"] for row in response.json()["keys"]}


@pytest.mark.anyio
async def test_put_then_get_round_trips(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """A value persisted via PUT is reflected on the next GET."""
    base = f"/api/v1/workspaces/{seeded_default_workspace.id}/env"
    put_response = await client.put(
        base,
        json={"vars": {"GEMINI_API_KEY": "real-key"}},
    )
    assert put_response.status_code == 200
    assert put_response.json()["vars"]["GEMINI_API_KEY"] == "real-key"

    get_response = await client.get(base)
    assert get_response.status_code == 200
    assert get_response.json()["vars"]["GEMINI_API_KEY"] == "real-key"


@pytest.mark.anyio
async def test_put_accepts_workspace_plugin_env_keys(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """Custom plugin env keys are stored in the workspace env file."""
    workspace_root = Path(seeded_default_workspace.path)
    _write_workspace_settings_plugin(workspace_root)
    base = f"/api/v1/workspaces/{seeded_default_workspace.id}/env"

    put_response = await client.put(
        base,
        json={"vars": {PLUGIN_TOKEN_KEY: "plugin-secret"}},
    )

    assert put_response.status_code == 200
    assert put_response.json()["vars"][PLUGIN_TOKEN_KEY] == "plugin-secret"
    assert keys.load_workspace_env(workspace_root)[PLUGIN_TOKEN_KEY] == "plugin-secret"


@pytest.mark.anyio
async def test_put_rejects_unknown_keys(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """Anything not in OVERRIDABLE_KEYS is a 400; never reaches save."""
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env",
        json={"vars": {"DATABASE_URL": "sneaky"}},
    )
    assert response.status_code == 400
    assert "DATABASE_URL" in response.json()["detail"]


@pytest.mark.anyio
async def test_put_rejects_newline_in_value(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """Newline characters trigger the validator and are rejected.

    Without this, a value of `valid\\nEXA_API_KEY=hijacked` would split
    into two lines on the next read and inject `EXA_API_KEY` for the
    workspace.
    """
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env",
        json={"vars": {"GEMINI_API_KEY": "good\nEXA_API_KEY=hijacked"}},
    )
    assert response.status_code == 422
    detail = str(response.json()["detail"])
    assert "newline" in detail.lower()


@pytest.mark.anyio
async def test_put_preserves_unmentioned_keys(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """PUT is PATCH-like: keys not in the payload are left untouched."""
    ws_root = Path(seeded_default_workspace.path)
    keys.save_workspace_env(
        ws_root,
        {"GEMINI_API_KEY": "keep-me", "EXA_API_KEY": "also-keep-me"},
    )
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env",
        json={"vars": {"GEMINI_API_KEY": "updated"}},
    )
    assert response.status_code == 200
    body = response.json()["vars"]
    assert body["GEMINI_API_KEY"] == "updated"
    assert body["EXA_API_KEY"] == "also-keep-me"


@pytest.mark.anyio
async def test_put_empty_string_clears_key(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """Sending `""` for a key removes it from the encrypted file.

    This is what the UI does when the user clears an input and saves.
    The resolver treats absent-on-disk and empty-string-on-disk
    identically (both fall through to settings); persisting `""` would
    be confusing on inspection, so we drop it.
    """
    ws_root = Path(seeded_default_workspace.path)
    keys.save_workspace_env(ws_root, {"GEMINI_API_KEY": "had-a-value"})
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env",
        json={"vars": {"GEMINI_API_KEY": ""}},
    )
    assert response.status_code == 200
    on_disk = keys.load_workspace_env(Path(seeded_default_workspace.path))
    assert "GEMINI_API_KEY" not in on_disk


@pytest.mark.anyio
async def test_delete_removes_one_key(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """DELETE drops a single key without touching the others."""
    ws_root = Path(seeded_default_workspace.path)
    keys.save_workspace_env(
        ws_root,
        {"GEMINI_API_KEY": "g", "EXA_API_KEY": "e"},
    )
    response = await client.delete(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env/GEMINI_API_KEY"
    )
    assert response.status_code == 204

    remaining = keys.load_workspace_env(Path(seeded_default_workspace.path))
    assert "GEMINI_API_KEY" not in remaining
    assert remaining.get("EXA_API_KEY") == "e"


@pytest.mark.anyio
async def test_delete_accepts_workspace_plugin_env_keys(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """DELETE uses the same workspace-specific plugin key allowlist."""
    ws_root = Path(seeded_default_workspace.path)
    _write_workspace_settings_plugin(ws_root)
    keys.save_workspace_env(ws_root, {PLUGIN_TOKEN_KEY: "plugin-secret"})

    response = await client.delete(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env/{PLUGIN_TOKEN_KEY}"
    )

    assert response.status_code == 204
    assert PLUGIN_TOKEN_KEY not in keys.load_workspace_env(ws_root)


@pytest.mark.anyio
async def test_delete_unknown_key_returns_404(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """Allowlist also gates DELETE."""
    response = await client.delete(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env/DATABASE_URL"
    )
    assert response.status_code == 404
