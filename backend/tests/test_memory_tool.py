"""Tests for the ``memory`` agent tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.tools.memory_tool import make_memory_tool

_SECTION_DELIMITER = "\n§\n"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def tool(workspace: Path):  # noqa: ANN201
    return make_memory_tool(workspace_root=workspace)


class TestAddAction:
    @pytest.mark.anyio
    async def test_add_creates_file_on_first_entry(
        self, tool, workspace: Path
    ) -> None:
        result = json.loads(
            await tool.execute("tc-1", action="add", target="memory", content="fact one")
        )
        assert result["success"] is True
        assert (workspace / "MEMORY.md").exists()
        assert "fact one" in (workspace / "MEMORY.md").read_text()

    @pytest.mark.anyio
    async def test_add_appends_with_delimiter(
        self, tool, workspace: Path
    ) -> None:
        await tool.execute("tc-1", action="add", target="memory", content="fact one")
        await tool.execute("tc-2", action="add", target="memory", content="fact two")
        content = (workspace / "MEMORY.md").read_text()
        assert "fact one" in content
        assert "fact two" in content
        assert _SECTION_DELIMITER in content

    @pytest.mark.anyio
    async def test_add_to_user_writes_user_md(
        self, tool, workspace: Path
    ) -> None:
        result = json.loads(
            await tool.execute("tc-1", action="add", target="user", content="Name: Alice")
        )
        assert result["success"] is True
        assert "Name: Alice" in (workspace / "USER.md").read_text()

    @pytest.mark.anyio
    async def test_add_rejects_when_cap_exceeded(
        self, tool, workspace: Path
    ) -> None:
        (workspace / "MEMORY.md").write_text("x" * 2100)
        result = json.loads(
            await tool.execute(
                "tc-1", action="add", target="memory", content="x" * 200
            )
        )
        assert result["success"] is False

    @pytest.mark.anyio
    async def test_add_returns_rendered_state(self, tool) -> None:
        result = json.loads(
            await tool.execute("tc-1", action="add", target="memory", content="hello")
        )
        assert "rendered_state" in result
        assert "hello" in result["rendered_state"]


class TestReplaceAction:
    @pytest.mark.anyio
    async def test_replace_swaps_matching_entry(
        self, tool, workspace: Path
    ) -> None:
        await tool.execute("tc-1", action="add", target="memory", content="old fact")
        result = json.loads(
            await tool.execute(
                "tc-2",
                action="replace",
                target="memory",
                old_text="old fact",
                content="new fact",
            )
        )
        assert result["success"] is True
        content = (workspace / "MEMORY.md").read_text()
        assert "new fact" in content
        assert "old fact" not in content

    @pytest.mark.anyio
    async def test_replace_fails_on_no_match(self, tool) -> None:
        await tool.execute("tc-1", action="add", target="memory", content="real fact")
        result = json.loads(
            await tool.execute(
                "tc-2",
                action="replace",
                target="memory",
                old_text="nonexistent",
                content="new",
            )
        )
        assert result["success"] is False


class TestRemoveAction:
    @pytest.mark.anyio
    async def test_remove_deletes_matching_entry(
        self, tool, workspace: Path
    ) -> None:
        await tool.execute("tc-1", action="add", target="memory", content="keep me")
        await tool.execute("tc-2", action="add", target="memory", content="drop me")
        result = json.loads(
            await tool.execute(
                "tc-3", action="remove", target="memory", old_text="drop me"
            )
        )
        assert result["success"] is True
        content = (workspace / "MEMORY.md").read_text()
        assert "keep me" in content
        assert "drop me" not in content

    @pytest.mark.anyio
    async def test_remove_fails_on_no_match(self, tool) -> None:
        await tool.execute("tc-1", action="add", target="memory", content="real fact")
        result = json.loads(
            await tool.execute(
                "tc-2", action="remove", target="memory", old_text="nonexistent"
            )
        )
        assert result["success"] is False


class TestValidation:
    @pytest.mark.anyio
    async def test_invalid_action_returns_error(self, tool) -> None:
        result = json.loads(
            await tool.execute("tc-1", action="bogus", target="memory", content="x")
        )
        assert result["success"] is False

    @pytest.mark.anyio
    async def test_invalid_target_returns_error(self, tool) -> None:
        result = json.loads(
            await tool.execute("tc-1", action="add", target="bogus", content="x")
        )
        assert result["success"] is False
