"""Tests for build_agent_tools — tool composition and send_fn gating."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.agent_tools import build_agent_tools


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Return a minimal workspace directory with required files."""
    (tmp_path / "AGENTS.md").write_text("# Test workspace")
    return tmp_path


def _make_send_fn() -> AsyncMock:
    """Return a no-op async send function."""
    return AsyncMock(return_value=None)


class TestBuildAgentToolsWithoutSendFn:
    """send_message tool must NOT appear when send_fn is omitted."""

    def test_send_message_absent_by_default(self, tmp_workspace: Path) -> None:
        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(workspace_root=tmp_workspace)

        names = [t.name for t in tools]
        assert "send_message" not in names

    def test_send_message_absent_when_send_fn_is_none(self, tmp_workspace: Path) -> None:
        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(workspace_root=tmp_workspace, send_fn=None)

        names = [t.name for t in tools]
        assert "send_message" not in names


class TestBuildAgentToolsWithSendFn:
    """send_message tool MUST appear when send_fn is provided."""

    def test_send_message_present_when_send_fn_provided(self, tmp_workspace: Path) -> None:
        send_fn = _make_send_fn()
        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(workspace_root=tmp_workspace, send_fn=send_fn)

        names = [t.name for t in tools]
        assert "send_message" in names

    def test_send_message_is_last_tool(self, tmp_workspace: Path) -> None:
        """send_message appended after workspace + artifact tools."""
        send_fn = _make_send_fn()
        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(workspace_root=tmp_workspace, send_fn=send_fn)

        assert tools[-1].name == "send_message"

    def test_other_tools_still_present_with_send_fn(self, tmp_workspace: Path) -> None:
        """Workspace and artifact tools survive alongside send_message."""
        send_fn = _make_send_fn()
        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(workspace_root=tmp_workspace, send_fn=send_fn)

        names = [t.name for t in tools]
        assert "render_artifact" in names
        # At least one workspace tool (read_file / write_file / list_files)
        assert any(n in names for n in ("read_file", "write_file", "list_files"))


class TestVirtualPythonGate:
    """``python`` tool only appears when ``virtual_python_enabled`` is True."""

    def test_python_absent_by_default(self, tmp_workspace: Path) -> None:
        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(workspace_root=tmp_workspace)

        names = [t.name for t in tools]
        assert "python" not in names

    def test_python_present_when_enabled(self, tmp_workspace: Path) -> None:
        with (
            patch("app.core.keys.resolve_api_key", return_value=None),
            patch("app.core.agent_tools.settings.virtual_python_enabled", True),
        ):
            tools = build_agent_tools(workspace_root=tmp_workspace)

        names = [t.name for t in tools]
        assert "python" in names

    def test_python_appears_before_send_message(self, tmp_workspace: Path) -> None:
        """Stable ordering: ``python`` sits between ``markitdown`` and ``send_message``."""
        send_fn = _make_send_fn()
        with (
            patch("app.core.keys.resolve_api_key", return_value=None),
            patch("app.core.agent_tools.settings.virtual_python_enabled", True),
        ):
            tools = build_agent_tools(workspace_root=tmp_workspace, send_fn=send_fn)

        names = [t.name for t in tools]
        assert names.index("python") < names.index("send_message")
