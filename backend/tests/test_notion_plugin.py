"""Tests for the Notion plugin.

Three concerns are exercised:

  * Registration — the plugin lands in :func:`all_plugins` with all 18
    tool factories.
  * ``call_ntn`` subprocess wrapping — token env injection, isolated
    ``HOME``, error surfacing.  Each test points ``NTN_BINARY`` at a
    small shell script written into the test tmpdir so we never need a
    real ``ntn`` install in CI.
  * Tool execute paths — every category gets one representative test
    that monkeypatches the ``call_ntn_*`` seam, runs ``tool.execute()``,
    and asserts the returned JSON shape + that an audit row was written.

Heavier scenario tests (multi-turn agent loop with the Notion plugin
loaded) belong in test_agent_loop_scenarios.py; this file stays at the
unit level.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plugins import ToolContext, all_plugins
from app.integrations.notion import notion_plugin
from app.integrations.notion.audit import STATUS_ERROR, STATUS_OK
from app.integrations.notion.ntn_client import NtnError, call_ntn
from app.integrations.notion.tools.comments import make_notion_comment_create_tool
from app.integrations.notion.tools.database import make_notion_query_tool
from app.integrations.notion.tools.diagnostics import (
    make_notion_help_tool,
    make_notion_logs_read_tool,
)
from app.integrations.notion.tools.lifecycle import make_notion_delete_tool
from app.integrations.notion.tools.read import make_notion_search_tool
from app.integrations.notion.tools.write import make_notion_create_tool
from app.models import NotionOperationLog, Workspace

NTN_BINARY_ENV_VAR = "NTN_BINARY"


@pytest.fixture
def ctx(seeded_default_workspace: Workspace, test_user) -> ToolContext:
    """Build a :class:`ToolContext` bound to the seeded workspace."""
    return ToolContext(
        workspace_id=seeded_default_workspace.id,
        workspace_root=Path(seeded_default_workspace.path),
        user_id=test_user.id,
        send_fn=None,
    )


@pytest.fixture
def patch_audit_sessionmaker(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession) -> None:
    """Route audit-log writes through the test's in-memory session.

    Production audit code uses ``app.db.async_session_maker`` directly so
    a tool call's audit row never participates in the caller's
    transaction (preventing audit failures from rolling back real work).
    In tests we want that row visible to the same ``db_session`` that
    the assertions query, so we monkeypatch the bound name in the audit
    module to a no-op context manager that yields the test session.
    """

    class _TestSessionContext:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *_: object) -> None:
            # Avoid double-commit / rollback — the production code calls
            # ``await session.commit()`` itself, which works fine on the
            # in-memory engine.
            return None

    def fake_maker() -> _TestSessionContext:
        return _TestSessionContext()

    monkeypatch.setattr("app.integrations.notion.audit.async_session_maker", fake_maker)
    monkeypatch.setattr("app.integrations.notion.tools.diagnostics.async_session_maker", fake_maker)


@pytest.fixture
def fake_ntn_binary(tmp_path: Path) -> Generator[Path]:
    """Create a shell stub at ``tmp_path/ntn`` that echoes a known string.

    Used by the ``call_ntn`` tests; tests that exercise tool factories
    monkeypatch the ``call_ntn_json`` / ``call_ntn_text`` seam directly
    and don't need this fixture.
    """
    script = tmp_path / "ntn"
    script.write_text(
        "#!/usr/bin/env bash\n"
        # Print the token + first arg so tests can assert env passthrough.
        'echo \'{"token":"\'$NOTION_API_TOKEN\'","first_arg":"\'$1\'"}\'\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    previous = os.environ.get(NTN_BINARY_ENV_VAR)
    os.environ[NTN_BINARY_ENV_VAR] = str(script)
    try:
        yield script
    finally:
        if previous is None:
            os.environ.pop(NTN_BINARY_ENV_VAR, None)
        else:
            os.environ[NTN_BINARY_ENV_VAR] = previous


class TestRegistration:
    def test_plugin_is_registered_with_eighteen_tools(self) -> None:
        ids = [p.id for p in all_plugins()]
        assert "notion" in ids
        # The registry is module-global and the plugin self-registers on
        # import; assert against the imported handle so an accidental
        # re-import wouldn't double-count.
        assert len(notion_plugin.tool_factories) == 18


class TestCallNtn:
    @pytest.mark.anyio
    async def test_returns_stdout_when_binary_exits_zero(self, fake_ntn_binary: Path) -> None:
        result = await call_ntn(["api", "v1/users/me"], token="secret-token")
        body = json.loads(result.stdout)
        assert body["token"] == "secret-token"
        assert body["first_arg"] == "api"

    @pytest.mark.anyio
    async def test_raises_ntn_error_when_binary_exits_nonzero(self, tmp_path: Path) -> None:
        script = tmp_path / "ntn"
        script.write_text("#!/usr/bin/env bash\necho 'boom' >&2\nexit 9\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        previous = os.environ.get(NTN_BINARY_ENV_VAR)
        os.environ[NTN_BINARY_ENV_VAR] = str(script)
        try:
            with pytest.raises(NtnError) as excinfo:
                await call_ntn(["api", "v1/users/me"], token="t")
            assert excinfo.value.returncode == 9
            assert "boom" in excinfo.value.stderr
        finally:
            if previous is None:
                os.environ.pop(NTN_BINARY_ENV_VAR, None)
            else:
                os.environ[NTN_BINARY_ENV_VAR] = previous


class TestToolFactories:
    @pytest.mark.anyio
    async def test_help_tool_returns_static_catalogue(self, ctx: ToolContext) -> None:
        tool = make_notion_help_tool(ctx)
        raw = await tool.execute("call-1")
        payload = json.loads(raw)
        names = {t["name"] for t in payload["tools"]}
        assert "notion_search" in names
        assert "notion_help" in names
        assert len(payload["tools"]) == 18

    @pytest.mark.anyio
    async def test_search_returns_missing_token_error_when_unconfigured(
        self, ctx: ToolContext
    ) -> None:
        tool = make_notion_search_tool(ctx)
        raw = await tool.execute("call-1", query="anything")
        body = json.loads(raw)
        assert "error" in body
        assert "Notion is not configured" in body["error"]

    @pytest.mark.anyio
    async def test_search_writes_audit_row_on_success(
        self,
        ctx: ToolContext,
        seeded_default_workspace: Workspace,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        patch_audit_sessionmaker: None,
    ) -> None:
        # Pretend the workspace has a token configured.
        monkeypatch.setattr(
            "app.integrations.notion.tools._helpers.resolve_api_key",
            lambda *_, **__: "tok-abc",
        )
        # Mock the subprocess seam so we don't need a real ntn binary.
        captured_args: list[list[str]] = []

        async def fake_call(args, *, token, **_):  # type: ignore[no-untyped-def]
            captured_args.append(list(args))
            return {"results": [{"id": "page-1", "object": "page"}]}

        monkeypatch.setattr("app.integrations.notion.tools.read.call_ntn_json", fake_call)

        tool = make_notion_search_tool(ctx)
        raw = await tool.execute("call-1", query="hello")
        body = json.loads(raw)
        assert body["results"][0]["id"] == "page-1"
        assert captured_args[0][:2] == ["api", "v1/search"]

        rows = (
            (
                await db_session.execute(
                    select(NotionOperationLog).where(
                        NotionOperationLog.workspace_id == seeded_default_workspace.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].tool_name == "notion_search"
        assert rows[0].status == STATUS_OK

    @pytest.mark.anyio
    async def test_search_writes_error_row_when_ntn_fails(
        self,
        ctx: ToolContext,
        seeded_default_workspace: Workspace,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        patch_audit_sessionmaker: None,
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.notion.tools._helpers.resolve_api_key",
            lambda *_, **__: "tok-abc",
        )

        async def fake_call(*_: Any, **__: Any) -> Any:
            raise NtnError(2, "unauthorized")

        monkeypatch.setattr("app.integrations.notion.tools.read.call_ntn_json", fake_call)

        tool = make_notion_search_tool(ctx)
        raw = await tool.execute("call-1", query="hello")
        body = json.loads(raw)
        assert "error" in body

        rows = (
            (
                await db_session.execute(
                    select(NotionOperationLog).where(
                        NotionOperationLog.workspace_id == seeded_default_workspace.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].status == STATUS_ERROR
        assert rows[0].error and "unauthorized" in rows[0].error

    @pytest.mark.anyio
    async def test_create_invokes_ntn_pages_create_with_markdown_arg(
        self,
        ctx: ToolContext,
        monkeypatch: pytest.MonkeyPatch,
        patch_audit_sessionmaker: None,
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.notion.tools._helpers.resolve_api_key",
            lambda *_, **__: "tok",
        )
        captured: list[list[str]] = []

        async def fake_call_text(args, *, token, **_):  # type: ignore[no-untyped-def]
            captured.append(list(args))
            return "Created page https://www.notion.so/abc"

        monkeypatch.setattr("app.integrations.notion.tools.write.call_ntn_text", fake_call_text)

        tool = make_notion_create_tool(ctx)
        raw = await tool.execute(
            "call-1",
            parent_page_id="parent-id",
            title="Hello",
            markdown="# H1",
        )
        body = json.loads(raw)
        assert "Created page" in body["output"]
        # ``--content`` arg carries the markdown verbatim — sanity-check
        # that we didn't accidentally drop it.
        assert "# H1" in captured[0]

    @pytest.mark.anyio
    async def test_query_rejects_missing_database_id(
        self, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.notion.tools._helpers.resolve_api_key",
            lambda *_, **__: "tok",
        )
        tool = make_notion_query_tool(ctx)
        raw = await tool.execute("call-1")
        assert "database_id is required" in json.loads(raw)["error"]

    @pytest.mark.anyio
    async def test_comment_create_validates_text(
        self, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.notion.tools._helpers.resolve_api_key",
            lambda *_, **__: "tok",
        )
        tool = make_notion_comment_create_tool(ctx)
        raw = await tool.execute("call-1", page_id="p", text="")
        assert "required" in json.loads(raw)["error"]

    @pytest.mark.anyio
    async def test_delete_sends_archived_true(
        self,
        ctx: ToolContext,
        monkeypatch: pytest.MonkeyPatch,
        patch_audit_sessionmaker: None,
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.notion.tools._helpers.resolve_api_key",
            lambda *_, **__: "tok",
        )
        captured: list[list[str]] = []

        async def fake_call(args, *, token, **_):  # type: ignore[no-untyped-def]
            captured.append(list(args))
            return {"id": "p", "archived": True}

        monkeypatch.setattr("app.integrations.notion.tools.lifecycle.call_ntn_json", fake_call)
        tool = make_notion_delete_tool(ctx)
        await tool.execute("call-1", page_id="p")
        # The PATCH body sits as the last arg (-d <body>).
        body_arg = captured[0][-1]
        assert json.loads(body_arg) == {"archived": True}

    @pytest.mark.anyio
    async def test_logs_read_returns_workspace_scoped_history(
        self,
        ctx: ToolContext,
        seeded_default_workspace: Workspace,
        db_session: AsyncSession,
        patch_audit_sessionmaker: None,
    ) -> None:
        # Seed two rows directly — bypasses the audit wrapper since
        # logs_read shouldn't depend on its own behaviour for the data
        # it surfaces.
        for tool_name in ("notion_search", "notion_read"):
            db_session.add(
                NotionOperationLog(
                    workspace_id=seeded_default_workspace.id,
                    tool_name=tool_name,
                    operation="read",
                    status=STATUS_OK,
                    duration_ms=12,
                    created_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
        await db_session.commit()

        tool = make_notion_logs_read_tool(ctx)
        raw = await tool.execute("call-1", limit=10)
        payload = json.loads(raw)
        names = {entry["tool_name"] for entry in payload["logs"]}
        assert names == {"notion_search", "notion_read"}
