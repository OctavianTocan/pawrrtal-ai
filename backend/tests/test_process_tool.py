"""Tests for the ``process`` agent tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.tools.process import _registry, make_process_tool


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    _registry.clear()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def tool(workspace: Path):  # noqa: ANN201
    return make_process_tool(workspace_root=workspace, conversation_id="conv-1")


def _parse(raw: str) -> dict:
    return json.loads(raw)


class TestStartAndList:
    @pytest.mark.anyio
    async def test_start_returns_pid(self, tool) -> None:
        result = _parse(await tool.execute("tc-1", action="start", command="sleep 10"))
        assert result["success"] is True
        assert "pid" in result

    @pytest.mark.anyio
    async def test_list_shows_running_process(self, tool) -> None:
        start = _parse(await tool.execute("tc-1", action="start", command="sleep 10"))
        pid = start["pid"]
        result = _parse(await tool.execute("tc-2", action="list"))
        assert any(p["pid"] == pid for p in result["processes"])

    @pytest.mark.anyio
    async def test_list_empty_when_no_processes(self, tool) -> None:
        result = _parse(await tool.execute("tc-1", action="list"))
        assert result["processes"] == []


class TestPollAndLog:
    @pytest.mark.anyio
    async def test_poll_returns_recent_output(self, tool) -> None:
        start = _parse(
            await tool.execute("tc-1", action="start", command="echo hello_poll")
        )
        pid = start["pid"]
        import asyncio
        await asyncio.sleep(0.3)
        result = _parse(await tool.execute("tc-2", action="poll", pid=pid))
        assert result["success"] is True
        assert "hello_poll" in result["output"]

    @pytest.mark.anyio
    async def test_log_returns_full_output(self, tool) -> None:
        start = _parse(
            await tool.execute("tc-1", action="start", command="echo hello_log")
        )
        pid = start["pid"]
        import asyncio
        await asyncio.sleep(0.3)
        result = _parse(await tool.execute("tc-2", action="log", pid=pid))
        assert result["success"] is True
        assert "hello_log" in result["output"]


class TestWait:
    @pytest.mark.anyio
    async def test_wait_returns_exit_code(self, tool) -> None:
        start = _parse(
            await tool.execute("tc-1", action="start", command="echo done")
        )
        pid = start["pid"]
        result = _parse(await tool.execute("tc-2", action="wait", pid=pid))
        assert result["success"] is True
        assert "exit_code" in result


class TestKill:
    @pytest.mark.anyio
    async def test_kill_terminates_process(self, tool) -> None:
        start = _parse(
            await tool.execute("tc-1", action="start", command="sleep 60")
        )
        pid = start["pid"]
        result = _parse(await tool.execute("tc-2", action="kill", pid=pid))
        assert result["success"] is True

    @pytest.mark.anyio
    async def test_kill_nonexistent_pid_fails(self, tool) -> None:
        result = _parse(await tool.execute("tc-1", action="kill", pid="fake-pid"))
        assert result["success"] is False


class TestWrite:
    @pytest.mark.anyio
    async def test_write_sends_stdin(self, tool) -> None:
        start = _parse(
            await tool.execute("tc-1", action="start", command="cat")
        )
        pid = start["pid"]
        result = _parse(
            await tool.execute("tc-2", action="write", pid=pid, input="hello\n")
        )
        assert result["success"] is True


class TestSubmit:
    @pytest.mark.anyio
    async def test_submit_sends_eof(self, tool) -> None:
        start = _parse(
            await tool.execute("tc-1", action="start", command="cat")
        )
        pid = start["pid"]
        result = _parse(
            await tool.execute("tc-2", action="submit", pid=pid)
        )
        assert result["success"] is True


class TestClose:
    @pytest.mark.anyio
    async def test_close_removes_from_registry(self, tool) -> None:
        start = _parse(
            await tool.execute("tc-1", action="start", command="echo bye")
        )
        pid = start["pid"]
        import asyncio
        await asyncio.sleep(0.2)
        _parse(await tool.execute("tc-2", action="close", pid=pid))
        result = _parse(await tool.execute("tc-3", action="list"))
        assert all(p["pid"] != pid for p in result["processes"])


class TestOwnership:
    @pytest.mark.anyio
    async def test_cannot_access_other_conversations_process(
        self, workspace: Path
    ) -> None:
        tool_a = make_process_tool(
            workspace_root=workspace, conversation_id="conv-a"
        )
        tool_b = make_process_tool(
            workspace_root=workspace, conversation_id="conv-b"
        )
        start = _parse(
            await tool_a.execute("tc-1", action="start", command="sleep 10")
        )
        pid = start["pid"]
        result = _parse(await tool_b.execute("tc-1", action="kill", pid=pid))
        assert result["success"] is False

    @pytest.mark.anyio
    async def test_list_only_shows_own_processes(
        self, workspace: Path
    ) -> None:
        tool_a = make_process_tool(
            workspace_root=workspace, conversation_id="conv-a"
        )
        tool_b = make_process_tool(
            workspace_root=workspace, conversation_id="conv-b"
        )
        await tool_a.execute("tc-1", action="start", command="sleep 10")
        result = _parse(await tool_b.execute("tc-1", action="list"))
        assert result["processes"] == []
