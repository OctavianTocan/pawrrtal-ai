"""Tests for the ``search_files`` agent tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.tools.search_files import make_search_files_tool


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "hello.py").write_text("def greet():\n    print('hello world')\n")
    (tmp_path / "utils.py").write_text("def helper():\n    return 42\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.py").write_text("# deep module\ndef greet_deep():\n    pass\n")
    return tmp_path


@pytest.fixture
def tool(workspace: Path):  # noqa: ANN201
    return make_search_files_tool(workspace_root=workspace)


class TestSearchFiles:
    @pytest.mark.anyio
    async def test_finds_matching_text(self, tool) -> None:
        result = await tool.execute("tc-1", query="greet")
        assert "hello.py" in result
        assert "greet" in result

    @pytest.mark.anyio
    async def test_returns_line_numbers(self, tool) -> None:
        result = await tool.execute("tc-1", query="hello world")
        assert "hello.py" in result

    @pytest.mark.anyio
    async def test_no_results_returns_message(self, tool) -> None:
        result = await tool.execute("tc-1", query="zzz_nonexistent_zzz")
        assert "no matches" in result.lower() or "0" in result

    @pytest.mark.anyio
    async def test_path_scopes_to_subdirectory(self, tool) -> None:
        result = await tool.execute("tc-1", query="greet", path="sub")
        assert "deep.py" in result
        assert "hello.py" not in result

    @pytest.mark.anyio
    async def test_include_filters_by_glob(self, tool) -> None:
        result = await tool.execute("tc-1", query="def", include="utils*")
        assert "utils.py" in result
        assert "hello.py" not in result

    @pytest.mark.anyio
    async def test_rejects_path_outside_workspace(self, tool) -> None:
        result = await tool.execute("tc-1", query="test", path="../../etc")
        assert "error" in result.lower() or "outside" in result.lower()
