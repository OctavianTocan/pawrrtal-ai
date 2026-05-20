"""Tests for the Notion plugin.

Three concerns are exercised:

  * Registration — the plugin lands in :func:`all_plugins` with a
    single ``ntn`` tool factory.
  * ``call_ntn`` subprocess wrapping — token env injection, isolated
    ``HOME``, error surfacing.  Each test points ``NTN_BINARY`` at a
    small shell script written into the test tmpdir so we never need a
    real ``ntn`` install in CI.
  * Tool execute paths — covers the missing-token gate, the happy path
    (audit row written, stdout/stderr returned), and the failure path
    (NtnError surfaced + error audit row).
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Generator, Sequence
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plugins import ToolContext, all_plugins
from app.db import User
from app.integrations.notion import notion_plugin
from app.integrations.notion.audit import STATUS_ERROR, STATUS_OK
from app.integrations.notion.ntn_client import NtnError, NtnResult, call_ntn
from app.integrations.notion.tool import make_ntn_tool
from app.models import NotionOperationLog, Workspace

NTN_BINARY_ENV_VAR = "NTN_BINARY"


@pytest.fixture
def ctx(seeded_default_workspace: Workspace, test_user: User) -> ToolContext:
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


@pytest.fixture
def fake_ntn_binary(tmp_path: Path) -> Generator[Path]:
    """Create a shell stub at ``tmp_path/ntn`` that echoes a known string.

    Used by the ``call_ntn`` tests; tests that exercise the tool
    factory monkeypatch the ``call_ntn`` seam directly and don't need
    this fixture.
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
    def test_plugin_is_registered_with_single_ntn_tool(self) -> None:
        ids = [p.id for p in all_plugins()]
        assert "notion" in ids
        # The registry is module-global and the plugin self-registers on
        # import; assert against the imported handle so an accidental
        # re-import wouldn't double-count.
        assert len(notion_plugin.tool_factories) == 1


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


class TestNtnTool:
    @pytest.mark.anyio
    async def test_returns_missing_token_error_when_unconfigured(self, ctx: ToolContext) -> None:
        tool = make_ntn_tool(ctx)
        raw = await tool.execute("call-1", args=["api", "v1/users/me"])
        body = json.loads(raw)
        assert "error" in body
        assert "Notion is not configured" in body["error"]

    @pytest.mark.anyio
    async def test_rejects_empty_args(
        self, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.notion.tool.resolve_api_key",
            lambda *_, **__: "tok",
        )
        tool = make_ntn_tool(ctx)
        raw = await tool.execute("call-1", args=[])
        body = json.loads(raw)
        assert "error" in body
        assert "non-empty list" in body["error"]

    @pytest.mark.anyio
    async def test_rejects_non_string_args_item(
        self, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dict in the args array would otherwise be Python-repr'd into
        an invalid CLI token. Reject explicitly so the agent gets a
        clear validation error instead of an opaque ``ntn`` failure.
        """
        monkeypatch.setattr(
            "app.integrations.notion.tool.resolve_api_key",
            lambda *_, **__: "tok",
        )
        tool = make_ntn_tool(ctx)
        raw = await tool.execute(
            "call-1",
            args=["api", "v1/pages/abc", "-X", "PATCH", "-d", {"archived": True}],
        )
        body = json.loads(raw)
        assert "error" in body
        assert "args[5]" in body["error"]
        assert "string" in body["error"]

    @pytest.mark.anyio
    async def test_coerces_single_string_into_one_arg(
        self,
        ctx: ToolContext,
        monkeypatch: pytest.MonkeyPatch,
        patch_audit_sessionmaker: None,
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.notion.tool.resolve_api_key",
            lambda *_, **__: "tok",
        )
        captured: list[list[str]] = []

        async def fake_call(args, *, token, stdin=None):  # type: ignore[no-untyped-def]
            captured.append(list(args))
            return NtnResult(stdout=b"ok", stderr=b"")

        monkeypatch.setattr("app.integrations.notion.tool.call_ntn", fake_call)

        tool = make_ntn_tool(ctx)
        await tool.execute("call-1", args="--help")
        assert captured == [["--help"]]

    @pytest.mark.anyio
    async def test_passes_args_verbatim_and_returns_stdout_stderr(
        self,
        ctx: ToolContext,
        seeded_default_workspace: Workspace,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        patch_audit_sessionmaker: None,
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.notion.tool.resolve_api_key",
            lambda *_, **__: "tok-abc",
        )
        captured_args: list[list[str]] = []
        captured_stdin: list[bytes | None] = []

        async def fake_call(
            args: Sequence[str],
            *,
            token: str,
            stdin: bytes | None = None,
            **_: Any,
        ) -> NtnResult:
            captured_args.append(list(args))
            captured_stdin.append(stdin)
            assert token == "tok-abc"
            return NtnResult(stdout=b'{"results":[]}\n', stderr=b"warn\n")

        monkeypatch.setattr("app.integrations.notion.tool.call_ntn", fake_call)

        tool = make_ntn_tool(ctx)
        raw = await tool.execute(
            "call-1",
            args=["api", "v1/search", "query==hello"],
            stdin="payload",
        )
        body = json.loads(raw)
        assert body["stdout"] == '{"results":[]}\n'
        assert body["stderr"] == "warn\n"
        assert captured_args[0] == ["api", "v1/search", "query==hello"]
        assert captured_stdin[0] == b"payload"

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
        assert rows[0].tool_name == "ntn"
        assert rows[0].operation == "cli"
        assert rows[0].status == STATUS_OK

    @pytest.mark.anyio
    async def test_writes_error_row_when_ntn_fails(
        self,
        ctx: ToolContext,
        seeded_default_workspace: Workspace,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        patch_audit_sessionmaker: None,
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.notion.tool.resolve_api_key",
            lambda *_, **__: "tok-abc",
        )

        async def fake_call(*_: Any, **__: Any) -> Any:
            raise NtnError(2, "unauthorized")

        monkeypatch.setattr("app.integrations.notion.tool.call_ntn", fake_call)

        tool = make_ntn_tool(ctx)
        raw = await tool.execute("call-1", args=["api", "v1/users/me"])
        body = json.loads(raw)
        assert "error" in body
        assert body["returncode"] == 2
        assert "unauthorized" in body["error"]

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
    async def test_surfaces_os_error_without_writing_audit_failure_row(
        self,
        ctx: ToolContext,
        monkeypatch: pytest.MonkeyPatch,
        patch_audit_sessionmaker: None,
    ) -> None:
        """An OSError (e.g. binary missing) is surfaced cleanly to the agent."""
        monkeypatch.setattr(
            "app.integrations.notion.tool.resolve_api_key",
            lambda *_, **__: "tok",
        )

        async def fake_call(*_: Any, **__: Any) -> Any:
            raise FileNotFoundError("ntn: command not found")

        monkeypatch.setattr("app.integrations.notion.tool.call_ntn", fake_call)
        tool = make_ntn_tool(ctx)
        raw = await tool.execute("call-1", args=["api", "v1/users/me"])
        body = json.loads(raw)
        assert "error" in body
        assert "command not found" in body["error"]
