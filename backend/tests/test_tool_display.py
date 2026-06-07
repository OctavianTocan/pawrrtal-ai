"""Tests for shared agent-tool display metadata."""

from __future__ import annotations

from pathlib import Path

from app.agents.types import AgentTool
from app.tools.display import (
    fallback_tool_display,
    render_tool_display,
    summarize_path,
    visible_argument_keys,
)
from app.tools.workspace_files import make_workspace_tools


async def _noop_execute(tool_call_id: str, **kwargs: object) -> str:
    return "ok"


def test_agent_tool_display_is_optional() -> None:
    tool = AgentTool(
        name="custom_tool",
        description="Custom",
        parameters={"type": "object"},
        execute=_noop_execute,
    )

    payload = render_tool_display(tool, {"content": "secret body"})

    assert payload["present"] == "🛠 Running Custom Tool"
    assert "content" not in payload["compact"]


def test_workspace_read_file_display_includes_path(tmp_path: Path) -> None:
    tool = next(t for t in make_workspace_tools(tmp_path) if t.name == "read_file")

    payload = render_tool_display(tool, {"path": "AGENTS.md"})

    assert payload["icon"] == "📖"
    assert payload["present"] == "📖 Reading AGENTS.md"
    assert payload["compact"] == "Read File -> AGENTS.md"


def test_summarize_path_keeps_tail_for_long_paths() -> None:
    path = "/Users/example/projects/workspace/backend/app/core/tools/display.py"

    assert summarize_path(path) == ".../tools/display.py"


def test_fallback_hides_sensitive_argument_keys() -> None:
    payload = fallback_tool_display(
        "upload_payload",
        {"path": "artifact.txt", "api_key": "secret", "content": "body"},
    )

    assert visible_argument_keys({"path": "x", "token": "y"}) == ["path"]
    assert payload["present"] == "🛠 Running Upload Payload (path)"
