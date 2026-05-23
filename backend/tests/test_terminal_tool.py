"""Tests for the ``terminal`` agent tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.tools.terminal import _conversation_cwd, make_terminal_tool

_CONV_ID = "test-conv"


@pytest.fixture(autouse=True)
def _clear_cwd_state() -> None:
    _conversation_cwd.clear()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "hello.txt").write_text("world\n")
    return tmp_path


@pytest.fixture
def tool(workspace: Path):  # noqa: ANN201
    return make_terminal_tool(workspace_root=workspace, conversation_id=_CONV_ID)


class TestBasicExecution:
    @pytest.mark.anyio
    async def test_runs_command_and_returns_output(self, tool) -> None:
        result = json.loads(await tool.execute("tc-1", command="echo hello"))
        assert result["exit_code"] == 0
        assert "hello" in result["output"]

    @pytest.mark.anyio
    async def test_captures_exit_code_on_failure(self, tool) -> None:
        result = json.loads(await tool.execute("tc-1", command="false"))
        assert result["exit_code"] != 0

    @pytest.mark.anyio
    async def test_reads_file_in_workspace(self, tool) -> None:
        result = json.loads(await tool.execute("tc-1", command="cat hello.txt"))
        assert "world" in result["output"]


class TestCwdTracking:
    @pytest.mark.anyio
    async def test_cwd_updates_after_cd(self, tool, workspace: Path) -> None:
        sub = workspace / "subdir"
        sub.mkdir()
        await tool.execute("tc-1", command="cd subdir")
        result = json.loads(await tool.execute("tc-2", command="pwd"))
        assert "subdir" in result["output"]

    @pytest.mark.anyio
    async def test_cwd_persists_after_failed_command(
        self, tool, workspace: Path
    ) -> None:
        sub = workspace / "subdir"
        sub.mkdir()
        await tool.execute("tc-1", command="cd subdir")
        await tool.execute("tc-2", command="false")
        result = json.loads(await tool.execute("tc-3", command="pwd"))
        assert "subdir" in result["output"]


class TestOutputTruncation:
    @pytest.mark.anyio
    async def test_long_output_is_truncated(self, tool) -> None:
        result = json.loads(
            await tool.execute(
                "tc-1",
                command="python3 -c \"print('x' * 60000)\"",
            )
        )
        assert len(result["output"]) < 60000
        assert "truncated" in result["output"].lower()

    @pytest.mark.anyio
    async def test_short_output_not_truncated(self, tool) -> None:
        result = json.loads(await tool.execute("tc-1", command="echo short"))
        assert "truncated" not in result["output"].lower()


class TestConversationIsolation:
    @pytest.mark.anyio
    async def test_different_conversations_have_independent_cwd(
        self, workspace: Path
    ) -> None:
        sub = workspace / "subdir"
        sub.mkdir()
        tool_a = make_terminal_tool(
            workspace_root=workspace, conversation_id="conv-a"
        )
        tool_b = make_terminal_tool(
            workspace_root=workspace, conversation_id="conv-b"
        )
        await tool_a.execute("tc-1", command="cd subdir")
        result_b = json.loads(await tool_b.execute("tc-1", command="pwd"))
        assert "subdir" not in result_b["output"]


class TestBashBoundary:
    @pytest.mark.anyio
    async def test_rm_outside_workspace_denied(self, tool) -> None:
        result = json.loads(
            await tool.execute("tc-1", command="rm /etc/passwd")
        )
        assert result["exit_code"] != 0 or "denied" in result.get("error", "").lower()
