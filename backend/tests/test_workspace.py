"""Tests for the workspace service and API.

Covers:

- ``seed_workspace``: Pawrrtal-owned root context files plus internal ``.agent`` shape.
- ``ensure_default_workspace`` / ``ensure_dev_admin_workspace``: idempotency, DB rows, orphan cleanup.
- Workspace API: list / tree / file read & write / skill discovery / path-traversal guard.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.keys import load_workspace_env
from app.core.persona_bootstrap import IDENTITY_BEGIN, IDENTITY_END
from app.core.workspace import _build_preferences_md, seed_workspace
from app.crud.workspace import (
    DEV_ADMIN_WORKSPACE_DIRNAME,
    create_workspace,
    ensure_default_workspace,
    ensure_dev_admin_workspace,
    get_default_workspace,
    list_workspaces,
)
from app.db import User
from app.models import UserPersonalization, Workspace


def _make_personalization(**kwargs: Any) -> UserPersonalization:
    """Build an unpersisted UserPersonalization for the workspace seeder."""
    defaults: dict[str, Any] = {
        "user_id": uuid.uuid4(),
        "name": "Tavi",
        "role": "Engineer",
        "company_website": "https://example.com",
        "linkedin": "https://linkedin.com/in/tavi",
        "goals": ["Build great products", "Automate toil"],
        "personality": "direct",
        "custom_instructions": None,
        "chatgpt_context": None,
        "connected_channels": None,
        "updated_at": datetime.now(UTC),
    }
    return UserPersonalization(**{**defaults, **kwargs})


def _patch_workspace_base(tmp_path: Path) -> Any:
    """Patch ``workspace_base_dir`` only; leave template paths real."""
    from app.core.config import settings

    return patch.object(settings, "workspace_base_dir", str(tmp_path))


# ---------------------------------------------------------------------------
# seed_workspace
# ---------------------------------------------------------------------------


class TestSeedWorkspace:
    def test_creates_required_root_files_and_symlinks(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id)
        for filename in (
            "AGENTS.md",
            "HEARTBEAT.md",
            "SOUL.md",
            "PREFERENCES.md",
            "USER.md",
        ):
            assert (root / filename).is_file(), f"missing {filename}"
        assert (root / ".env").is_file()
        assert load_workspace_env(root) == {}
        assert (root / "CLAUDE.md").is_symlink()
        assert (root / "CLAUDE.md").readlink() == Path("AGENTS.md")
        assert (root / ".agents" / "skills").is_symlink()
        assert (root / ".agents" / "skills").readlink() == Path("../.agent/skills")
        assert (root / ".claude" / "skills").is_symlink()
        assert (root / ".claude" / "skills").readlink() == Path("../.agent/skills")

    def test_agent_directory_contains_only_internal_roots(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id)
        agent_children = {entry.name for entry in (root / ".agent").iterdir()}
        assert agent_children == {"memory", "protocols", "harness", "tools", "skills"}

    def test_creates_internal_directories(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id)
        for directory in ("memory", "protocols", "harness", "tools", "skills"):
            assert (root / ".agent" / directory).is_dir(), f"missing {directory}/"

    def test_copies_protocols(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id)
        protocols = root / ".agent" / "protocols"
        assert (protocols / "permissions.md").exists()
        assert (protocols / "delegation.md").exists()
        assert (protocols / "hook_patterns.json").exists()

    def test_copies_paw_skills(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id)
        for name in ("paw-persona", "paw-bootstrap"):
            assert (root / ".agent" / "skills" / name / "SKILL.md").exists()
        assert (root / ".agent" / "skills" / "_index.md").exists()

    def test_seeds_root_heartbeat(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id)
        heartbeat = root / "HEARTBEAT.md"
        assert heartbeat.exists()
        assert "checks:" in heartbeat.read_text(encoding="utf-8")

    def test_preferences_md_seeded_with_identity_block(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id)
        prefs = (root / "PREFERENCES.md").read_text(encoding="utf-8")
        assert IDENTITY_BEGIN in prefs
        assert IDENTITY_END in prefs
        # The block is parseable JSON with bootstrap_completed false on first seed.
        block = prefs.split(IDENTITY_BEGIN, 1)[1].split(IDENTITY_END, 1)[0].strip()
        payload = json.loads(block)
        assert payload["bootstrap_completed"] is False

    def test_preferences_md_includes_personalization(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        p = _make_personalization(name="Alice", role="PM")
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id, personalization=p)
        prefs = (root / "PREFERENCES.md").read_text(encoding="utf-8")
        assert "Alice" in prefs
        assert "PM" in prefs

    def test_preferences_md_renders_placeholder_without_personalization(
        self, tmp_path: Path
    ) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id, personalization=None)
        prefs = (root / "PREFERENCES.md").read_text(encoding="utf-8")
        assert "first-run setup" in prefs

    def test_reseed_does_not_overwrite_edited_files(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id)
            edited = root / "AGENTS.md"
            edited.write_text("hand-edited", encoding="utf-8")
            seed_workspace(ws_id)
        assert edited.read_text(encoding="utf-8") == "hand-edited"

    def test_reseed_does_not_overwrite_edited_preferences(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        with _patch_workspace_base(tmp_path):
            root = seed_workspace(ws_id)
            prefs = root / "PREFERENCES.md"
            prefs.write_text("user has typed in here", encoding="utf-8")
            seed_workspace(ws_id, personalization=_make_personalization(name="Bob"))
        assert prefs.read_text(encoding="utf-8") == "user has typed in here"

    def test_conflicting_real_symlink_path_raises(self, tmp_path: Path) -> None:
        ws_id = uuid.uuid4()
        root = tmp_path / str(ws_id)
        (root / ".agents" / "skills").mkdir(parents=True)
        with _patch_workspace_base(tmp_path), pytest.raises(FileExistsError):
            seed_workspace(ws_id)


# ---------------------------------------------------------------------------
# _build_preferences_md
# ---------------------------------------------------------------------------


class TestBuildPreferencesMd:
    def test_includes_identity_block_with_bootstrap_pending(self) -> None:
        md = _build_preferences_md(None)
        assert IDENTITY_BEGIN in md
        assert IDENTITY_END in md
        block = md.split(IDENTITY_BEGIN, 1)[1].split(IDENTITY_END, 1)[0].strip()
        assert json.loads(block)["bootstrap_completed"] is False

    def test_includes_name_role_company(self) -> None:
        p = _make_personalization(name="Bob", role="CTO", company_website="https://acme.com")
        md = _build_preferences_md(p)
        assert "Bob" in md
        assert "CTO" in md
        assert "https://acme.com" in md

    def test_includes_goals_list(self) -> None:
        p = _make_personalization(goals=["Ship fast", "Sleep well"])
        md = _build_preferences_md(p)
        assert "Ship fast" in md
        assert "Sleep well" in md

    def test_includes_custom_instructions(self) -> None:
        p = _make_personalization(custom_instructions="Always use British English.")
        md = _build_preferences_md(p)
        assert "British English" in md

    def test_none_personalization_renders_placeholder(self) -> None:
        md = _build_preferences_md(None)
        assert "first-run setup" in md


# ---------------------------------------------------------------------------
# DB service functions
# ---------------------------------------------------------------------------


class TestWorkspaceService:
    @pytest.mark.anyio
    async def test_create_workspace_adds_db_row(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        assert ws.id is not None
        assert ws.user_id == test_user.id
        assert ws.name == "Main"
        assert ws.is_default is True

    @pytest.mark.anyio
    async def test_create_workspace_seeds_filesystem(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        root = Path(ws.path)
        assert (root / "AGENTS.md").exists()
        assert (root / ".agent" / "memory").is_dir()

    @pytest.mark.anyio
    async def test_get_default_workspace_returns_none_when_absent(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        result = await get_default_workspace(test_user.id, db_session)
        assert result is None

    @pytest.mark.anyio
    async def test_get_default_workspace_returns_existing(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            created = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        fetched = await get_default_workspace(test_user.id, db_session)
        assert fetched is not None
        assert fetched.id == created.id

    @pytest.mark.anyio
    async def test_ensure_default_workspace_is_idempotent(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws1 = await ensure_default_workspace(test_user.id, db_session)
            await db_session.commit()
            ws2 = await ensure_default_workspace(test_user.id, db_session)
            await db_session.commit()

        assert ws1.id == ws2.id

    @pytest.mark.anyio
    async def test_ensure_dev_admin_workspace_uses_stable_path(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await ensure_dev_admin_workspace(test_user.id, db_session)
            await db_session.commit()

        assert ws.path == str(tmp_path / DEV_ADMIN_WORKSPACE_DIRNAME)
        assert (Path(ws.path) / "AGENTS.md").exists()

    @pytest.mark.anyio
    async def test_ensure_dev_admin_workspace_preserves_existing_files(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        """DB-reset run: dev-admin folder already has user files; helper
        must reuse the folder without overwriting them."""

        stable_root = tmp_path / DEV_ADMIN_WORKSPACE_DIRNAME
        stable_root.mkdir(parents=True)
        user_file = stable_root / ".agent" / "memory" / "personal" / "my-notes.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("important user content", encoding="utf-8")
        # Pre-existing seed file with edited content must not be clobbered.
        edited_agents = stable_root / "AGENTS.md"
        edited_agents.write_text("hand-edited", encoding="utf-8")

        with _patch_workspace_base(tmp_path):
            ws = await ensure_dev_admin_workspace(test_user.id, db_session)
            await db_session.commit()

        assert ws.path == str(stable_root)
        assert user_file.read_text(encoding="utf-8") == "important user content"
        assert edited_agents.read_text(encoding="utf-8") == "hand-edited"

    @pytest.mark.anyio
    async def test_ensure_dev_admin_workspace_is_idempotent(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws1 = await ensure_dev_admin_workspace(test_user.id, db_session)
            await db_session.commit()
            ws2 = await ensure_dev_admin_workspace(test_user.id, db_session)
            await db_session.commit()

        assert ws1.id == ws2.id
        assert ws1.path == ws2.path

    @pytest.mark.anyio
    async def test_list_workspaces_empty_for_new_user(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        workspaces = await list_workspaces(test_user.id, db_session)
        assert workspaces == []

    @pytest.mark.anyio
    async def test_list_workspaces_returns_all(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            await create_workspace(test_user.id, db_session, name="Main", slug="main")
            await create_workspace(
                test_user.id, db_session, name="Work", slug="work", is_default=False
            )
            await db_session.commit()

        workspaces = await list_workspaces(test_user.id, db_session)
        assert len(workspaces) == 2

    @pytest.mark.anyio
    async def test_unique_index_blocks_duplicate_default_insert(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        """Regression for pawrrtal-pq4r: partial unique index actually fires."""
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        await db_session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_workspaces_one_default_per_user "
                "ON workspaces (user_id) "
                "WHERE is_default = true"
            )
        )
        await db_session.commit()

        with _patch_workspace_base(tmp_path):
            ws1 = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        caught = False
        with _patch_workspace_base(tmp_path):
            try:
                async with db_session.begin_nested():
                    await create_workspace(test_user.id, db_session)
            except SAIntegrityError:
                caught = True

        assert caught, "Expected IntegrityError from unique index"

        from sqlalchemy import func
        from sqlalchemy import select as sa_select

        from app.models import Workspace

        count_result = await db_session.execute(
            sa_select(func.count())
            .select_from(Workspace)
            .where(
                Workspace.user_id == test_user.id,
                Workspace.is_default.is_(True),
            )
        )
        assert count_result.scalar_one() == 1
        result = await get_default_workspace(test_user.id, db_session)
        assert result is not None
        assert result.id == ws1.id

    @pytest.mark.anyio
    async def test_ensure_default_workspace_handles_integrity_error(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        """ensure_default_workspace recovers cleanly when a concurrent
        request already committed the workspace."""
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        with _patch_workspace_base(tmp_path):
            real_ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        with (
            _patch_workspace_base(tmp_path),
            patch(
                "app.crud.workspace.create_workspace",
                side_effect=SAIntegrityError("mock", {}, Exception()),
            ),
        ):
            recovered_ws = await ensure_default_workspace(test_user.id, db_session)

        assert recovered_ws.id == real_ws.id

    @pytest.mark.anyio
    async def test_ensure_default_workspace_removes_orphan_dir_after_integrity_error(
        self,
        tmp_path: Path,
    ) -> None:
        """The losing concurrent insert must not leave a seeded directory behind."""
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        class FailingSavepoint:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, *_args: object) -> None:
                raise SAIntegrityError("mock", {}, Exception())

        user_id = uuid.uuid4()
        orphan = tmp_path / str(uuid.uuid4())
        orphan.mkdir()
        winner = SimpleNamespace(id=uuid.uuid4())

        def begin_nested() -> FailingSavepoint:
            return FailingSavepoint()

        fake_session = SimpleNamespace(begin_nested=begin_nested)

        with (
            patch("app.crud.workspace.settings") as mock_settings,
            patch(
                "app.crud.workspace.get_default_workspace",
                new=AsyncMock(side_effect=[None, winner]),
            ),
            patch(
                "app.crud.workspace.create_workspace",
                new=AsyncMock(return_value=SimpleNamespace(path=str(orphan))),
            ),
        ):
            mock_settings.workspace_base_dir = str(tmp_path)
            recovered_ws = await ensure_default_workspace(
                user_id, cast("AsyncSession", fake_session)
            )

        assert recovered_ws is cast("Workspace", winner)
        assert not orphan.exists()


# ---------------------------------------------------------------------------
# Workspace API
# ---------------------------------------------------------------------------


class TestWorkspaceAPI:
    @pytest.mark.anyio
    async def test_list_workspaces_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/workspaces")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_list_workspaces_returns_created(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            await create_workspace(test_user.id, db_session)
            await db_session.commit()

        resp = await client.get("/api/v1/workspaces")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Main"

    @pytest.mark.anyio
    async def test_tree_returns_agent_dir(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        resp = await client.get(f"/api/v1/workspaces/{ws.id}/tree")
        assert resp.status_code == 200
        names = {node["name"] for node in resp.json()["nodes"]}
        assert ".agent" in names

    @pytest.mark.anyio
    async def test_tree_returns_404_for_unknown_workspace(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/workspaces/{uuid.uuid4()}/tree")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_read_file_returns_content(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        resp = await client.get(f"/api/v1/workspaces/{ws.id}/files/AGENTS.md")
        assert resp.status_code == 200
        assert "Pawrrtal workspace" in resp.json()["content"]

    @pytest.mark.anyio
    async def test_read_file_404_for_missing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        resp = await client.get(f"/api/v1/workspaces/{ws.id}/files/DOES_NOT_EXIST.md")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_write_then_read_file(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        content = "# My Note\n\nHello from the test.\n"
        put_resp = await client.put(
            f"/api/v1/workspaces/{ws.id}/files/.agent/memory/working/2026-05-06.md",
            json={"content": content},
        )
        assert put_resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/workspaces/{ws.id}/files/.agent/memory/working/2026-05-06.md"
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["content"] == content

    @pytest.mark.anyio
    async def test_write_symlink_path_is_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        resp = await client.put(
            f"/api/v1/workspaces/{ws.id}/files/CLAUDE.md",
            json={"content": "do not alias"},
        )

        assert resp.status_code == 400
        assert (Path(ws.path) / "CLAUDE.md").is_symlink()
        assert "do not alias" not in (Path(ws.path) / "AGENTS.md").read_text(encoding="utf-8")

    @pytest.mark.anyio
    async def test_write_through_symlink_directory_is_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        resp = await client.put(
            f"/api/v1/workspaces/{ws.id}/files/.claude/skills/new/SKILL.md",
            json={"content": "do not alias"},
        )

        assert resp.status_code == 400
        assert not (Path(ws.path) / ".agent" / "skills" / "new" / "SKILL.md").exists()

    @pytest.mark.anyio
    async def test_delete_file(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        await client.put(
            f"/api/v1/workspaces/{ws.id}/files/.agent/memory/working/output.txt",
            json={"content": "some output"},
        )
        del_resp = await client.delete(
            f"/api/v1/workspaces/{ws.id}/files/.agent/memory/working/output.txt"
        )
        assert del_resp.status_code == 204

        get_resp = await client.get(
            f"/api/v1/workspaces/{ws.id}/files/.agent/memory/working/output.txt"
        )
        assert get_resp.status_code == 404

    @pytest.mark.anyio
    async def test_delete_symlink_removes_link_not_target(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        root = Path(ws.path)
        del_resp = await client.delete(f"/api/v1/workspaces/{ws.id}/files/CLAUDE.md")

        assert del_resp.status_code == 204
        assert not (root / "CLAUDE.md").exists()
        assert (root / "AGENTS.md").exists()

    @pytest.mark.anyio
    async def test_delete_through_symlink_directory_is_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        target = Path(ws.path) / ".agent" / "skills" / "paw-bootstrap" / "SKILL.md"
        del_resp = await client.delete(
            f"/api/v1/workspaces/{ws.id}/files/.claude/skills/paw-bootstrap/SKILL.md"
        )

        assert del_resp.status_code == 400
        assert target.exists()

    @pytest.mark.anyio
    async def test_path_traversal_is_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        resp = await client.get(f"/api/v1/workspaces/{ws.id}/files/../../../etc/passwd")
        assert resp.status_code in (400, 404)

    @pytest.mark.anyio
    async def test_skills_endpoint_returns_seeded_skills(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

        resp = await client.get(f"/api/v1/workspaces/{ws.id}/skills")
        assert resp.status_code == 200
        names = {row["name"] for row in resp.json()}
        assert names == {"paw-persona", "paw-bootstrap", "heartbeat"}


class TestWorkspaceCrudAPI:
    """POST/PATCH/DELETE /api/v1/workspaces — exposed so external clients
    (paw, future SDKs) can manage workspaces without piggybacking on the
    personalization side-effect.
    """

    @pytest.mark.anyio
    async def test_create_workspace_returns_201(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            resp = await client.post(
                "/api/v1/workspaces",
                json={"name": "Project Alpha"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Project Alpha"
        assert body["is_default"] is True  # first workspace becomes default
        assert body["path"].startswith(str(tmp_path))

    @pytest.mark.anyio
    async def test_create_workspace_duplicate_name_is_409(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            first = await client.post("/api/v1/workspaces", json={"name": "Main"})
            assert first.status_code == 201
            second = await client.post("/api/v1/workspaces", json={"name": "Main"})
        assert second.status_code == 409

    @pytest.mark.anyio
    async def test_create_workspace_rejects_path_outside_base(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        with _patch_workspace_base(tmp_path):
            resp = await client.post(
                "/api/v1/workspaces",
                json={"name": "Outside", "path": "/etc"},
            )
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_patch_workspace_renames(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session)
            await db_session.commit()

            resp = await client.patch(
                f"/api/v1/workspaces/{ws.id}",
                json={"name": "Renamed"},
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    @pytest.mark.anyio
    async def test_delete_workspace_removes_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            # Two workspaces so deleting the non-default one is allowed.
            await create_workspace(
                test_user.id, db_session, name="Default", is_default=True
            )
            secondary = await create_workspace(
                test_user.id, db_session, name="Side", slug="side", is_default=False
            )
            await db_session.commit()

            resp = await client.delete(f"/api/v1/workspaces/{secondary.id}")
            assert resp.status_code == 204

            follow_up = await client.get(f"/api/v1/workspaces/{secondary.id}/tree")
            assert follow_up.status_code == 404

    @pytest.mark.anyio
    async def test_delete_default_workspace_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            await create_workspace(
                test_user.id, db_session, name="Default", is_default=True
            )
            secondary = await create_workspace(
                test_user.id, db_session, name="Side", slug="side", is_default=False
            )
            await db_session.commit()
            # Try to delete the default workspace; should fail.
            default_ws = await get_default_workspace(test_user.id, db_session)
            assert default_ws is not None

            resp = await client.delete(f"/api/v1/workspaces/{default_ws.id}")
        assert resp.status_code == 409
        # Sanity: secondary still exists.
        assert secondary.id != default_ws.id

    @pytest.mark.anyio
    async def test_delete_last_workspace_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        tmp_path: Path,
    ) -> None:
        with _patch_workspace_base(tmp_path):
            ws = await create_workspace(test_user.id, db_session, is_default=False)
            await db_session.commit()

            resp = await client.delete(f"/api/v1/workspaces/{ws.id}")
        assert resp.status_code == 409
