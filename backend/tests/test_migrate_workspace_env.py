"""Tests for the one-time user-keyed → workspace-keyed env migration helper.

The unit-level behaviour (single-file migrate, idempotency, conflict
quarantine) is exercised here; the startup-time wiring in ``main.py``
is covered indirectly by the existing app boot tests.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.core import keys
from app.core.config import settings


@pytest.fixture
def isolate_workspace_base(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point ``keys.py`` at a per-test temp directory."""
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    return tmp_path


def _write_legacy_env(base: Path, user_id: uuid.UUID, payload: dict[str, str]) -> Path:
    """Drop a legacy user-keyed encrypted env file into the fake base dir."""
    user_dir = base / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    # Re-use the production save helper but write to the legacy *user* path.
    # We do that by temporarily aliasing: easier to assemble the encrypted
    # bytes directly via the same Fernet the resolver uses.
    plaintext = "\n".join(f"{k}={v}" for k, v in payload.items() if v)
    # Access the cached Fernet instance through the public load/save helpers
    # would write to the new (workspace) path; we want the *legacy* path,
    # so go through the internal serializer + Fernet to lay the bytes down.
    fernet = keys._fernet()
    (user_dir / ".env").write_bytes(fernet.encrypt(plaintext.encode()))
    (user_dir / ".env").chmod(0o600)
    return user_dir / ".env"


class TestMigrateUserKeyedEnvFile:
    def test_returns_false_when_no_legacy_file_exists(self, isolate_workspace_base: Path) -> None:
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        result = keys.migrate_user_keyed_env_file(
            user_id=user_id, default_workspace_id=workspace_id
        )

        assert result is False

    def test_moves_legacy_file_into_workspace_dir(self, isolate_workspace_base: Path) -> None:
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        _write_legacy_env(isolate_workspace_base, user_id, {"GEMINI_API_KEY": "from-legacy"})

        result = keys.migrate_user_keyed_env_file(
            user_id=user_id, default_workspace_id=workspace_id
        )

        assert result is True
        # The new path is readable through the public resolver.
        loaded = keys.load_workspace_env(workspace_id)
        assert loaded == {"GEMINI_API_KEY": "from-legacy"}

    def test_legacy_file_renamed_after_migration(self, isolate_workspace_base: Path) -> None:
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        legacy_path = _write_legacy_env(isolate_workspace_base, user_id, {"EXA_API_KEY": "x"})

        keys.migrate_user_keyed_env_file(user_id=user_id, default_workspace_id=workspace_id)

        # Source is renamed (not deleted) so the move is reversible.
        assert not legacy_path.exists()
        siblings = list(legacy_path.parent.iterdir())
        assert any(s.name.startswith(".env.migrated-") for s in siblings)

    def test_idempotent_second_call_is_noop(self, isolate_workspace_base: Path) -> None:
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        _write_legacy_env(isolate_workspace_base, user_id, {"EXA_API_KEY": "x"})

        first = keys.migrate_user_keyed_env_file(user_id=user_id, default_workspace_id=workspace_id)
        second = keys.migrate_user_keyed_env_file(
            user_id=user_id, default_workspace_id=workspace_id
        )

        assert first is True
        assert second is False

    def test_existing_destination_quarantines_legacy_source(
        self, isolate_workspace_base: Path
    ) -> None:
        """When the workspace already has a ``.env``, the legacy file is
        quarantined rather than overwriting the destination."""
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        # Pre-existing workspace-keyed env (the "new" value to preserve).
        keys.save_workspace_env(workspace_id, {"EXA_API_KEY": "workspace-value"})
        # Legacy file with a conflicting value.
        legacy_path = _write_legacy_env(
            isolate_workspace_base, user_id, {"EXA_API_KEY": "legacy-value"}
        )

        result = keys.migrate_user_keyed_env_file(
            user_id=user_id, default_workspace_id=workspace_id
        )

        assert result is False
        # Workspace value is untouched.
        assert keys.load_workspace_env(workspace_id) == {"EXA_API_KEY": "workspace-value"}
        # Legacy file was quarantined.
        assert not legacy_path.exists()
