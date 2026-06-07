"""Security tests for the active recall plugin and workspace tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.workspace_files import make_workspace_tools


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with both safe and forbidden files."""
    (tmp_path / "AGENTS.md").write_text("# Agent rules\n", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=secret_val\n", encoding="utf-8")
    (tmp_path / "private.pem").write_text("PEM_DATA\n", encoding="utf-8")
    return tmp_path


@pytest.mark.anyio
async def test_list_dir_filters_out_forbidden_filenames(workspace: Path) -> None:
    """Verify that forbidden filenames are hidden from directory listings."""
    tools = {tool.name: tool for tool in make_workspace_tools(workspace)}
    list_dir_tool = tools["list_dir"]

    out = await list_dir_tool.execute("call-1")
    assert "AGENTS.md" in out
    assert ".env" not in out
    assert "private.pem" not in out
