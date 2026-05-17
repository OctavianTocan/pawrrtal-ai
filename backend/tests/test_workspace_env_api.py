"""HTTP-level tests for the /api/v1/workspaces/{workspace_id}/env router.

Exercises the actual endpoints (not the helpers in keys.py — those have
their own unit tests in test_keys.py). Covers:

  * GET returns every overridable key with empty defaults for unset workspaces.
  * GET reflects what was previously persisted via PUT.
  * PUT happy path round-trips through encryption.
  * PUT rejects an unknown key with 400 (allowlist enforcement).
  * PUT rejects values longer than MAX_VALUE_LENGTH with 422.
  * PUT rejects newline injection with 422 (validator-level guard).
  * PUT rejects more than MAX_KEYS keys with 422.
  * PUT preserves keys not mentioned in the payload (PATCH semantics).
  * PUT with empty-string strips the key on disk (works as "clear" path).
  * DELETE removes a single key idempotently.
  * DELETE on an unknown key returns 404.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.api.workspace_env import MAX_KEYS, MAX_VALUE_LENGTH
from app.core import keys
from app.core.config import settings
from app.models import Workspace


@pytest.fixture
def isolate_workspace_base(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point keys.py at a per-test temp directory, isolating the filesystem.

    Same pattern used by test_keys.py — re-pointed live so individual
    `_workspace_env_path` calls pick it up without re-importing.
    """
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    return tmp_path


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
    expected_keys = {
        "GEMINI_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "EXA_API_KEY",
        "XAI_API_KEY",
        "OPENAI_CODEX_OAUTH_TOKEN",
        "NOTION_API_KEY",
    }
    assert set(body["vars"].keys()) == expected_keys
    assert all(v == "" for v in body["vars"].values())


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
async def test_put_rejects_oversized_values(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """A value longer than MAX_VALUE_LENGTH is a 422."""
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env",
        json={"vars": {"GEMINI_API_KEY": "x" * (MAX_VALUE_LENGTH + 1)}},
    )
    assert response.status_code == 422


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
async def test_put_rejects_too_many_keys(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """More than MAX_KEYS distinct entries trips the safety bound.

    The allowlist itself is 4 keys today, so to actually trigger the
    MAX_KEYS check we have to send extras (which would individually
    fail the allowlist check first). This test asserts the ordering:
    the count check fires first.
    """
    bogus = {f"BOGUS_KEY_{i}": "x" for i in range(MAX_KEYS + 1)}
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env",
        json={"vars": bogus},
    )
    assert response.status_code == 422
    assert f"maximum is {MAX_KEYS}" in response.json()["detail"]


@pytest.mark.anyio
async def test_put_preserves_unmentioned_keys(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """PUT is PATCH-like: keys not in the payload are left untouched."""
    keys.save_workspace_env(
        seeded_default_workspace.id,
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
    keys.save_workspace_env(seeded_default_workspace.id, {"GEMINI_API_KEY": "had-a-value"})
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env",
        json={"vars": {"GEMINI_API_KEY": ""}},
    )
    assert response.status_code == 200
    on_disk = keys.load_workspace_env(seeded_default_workspace.id)
    assert "GEMINI_API_KEY" not in on_disk


@pytest.mark.anyio
async def test_delete_removes_one_key(
    client: AsyncClient,
    isolate_workspace_base: Path,
    seeded_default_workspace: Workspace,
) -> None:
    """DELETE drops a single key without touching the others."""
    keys.save_workspace_env(
        seeded_default_workspace.id,
        {"GEMINI_API_KEY": "g", "EXA_API_KEY": "e"},
    )
    response = await client.delete(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/env/GEMINI_API_KEY"
    )
    assert response.status_code == 204

    remaining = keys.load_workspace_env(seeded_default_workspace.id)
    assert "GEMINI_API_KEY" not in remaining
    assert remaining.get("EXA_API_KEY") == "e"


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
