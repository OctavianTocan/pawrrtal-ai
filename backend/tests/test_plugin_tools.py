"""Tests for manifest-backed plugin tools in agent tool composition."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from app.agents.tools import build_agent_tools
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state


def _write_cli_plugin(
    workspace_root: Path,
    *,
    plugin_id: str = "echo_plugin",
    capability_id: str = "echo_tool",
    exposure: str = "direct_and_catalog",
    enabled: bool = True,
) -> None:
    """Write a workspace CLI plugin and matching state."""
    plugin_dir = workspace_root / ".agent" / "plugins" / plugin_id
    plugin_dir.mkdir(parents=True)
    code = "import json, sys; print(json.dumps({'args': sys.argv[1:]}))"
    payload = {
        "schema_version": 1,
        "id": plugin_id,
        "name": plugin_id.replace("_", " ").title(),
        "version": "1.0.0",
        "description": "Echo plugin used by dynamic tool composition tests.",
        "permissions": ["subprocess"],
        "capabilities": [
            {
                "type": "cli_tool",
                "id": capability_id,
                "tool_name": capability_id,
                "title": "Echo Tool",
                "description": "Echo CLI arguments through a JSON subprocess.",
                "exposure": exposure,
                "entrypoint": ["python3", "-c", code],
                "args_schema": {
                    "type": "object",
                    "properties": {"args": {"type": "array", "items": {"type": "string"}}},
                    "required": [],
                },
            }
        ],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")
    save_plugin_state(
        plugin_state_path(
            plugin_id=plugin_id,
            scope="workspace",
            workspace_root=workspace_root,
        ),
        PluginState(enabled=enabled),
    )


def _tool_names(workspace_root: Path) -> set[str]:
    """Return tool names for a synthetic authenticated turn."""
    return {
        tool.name
        for tool in build_agent_tools(
            workspace_root=workspace_root,
            user_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )
    }


def test_direct_workspace_cli_plugin_is_exposed_and_runs(tmp_path: Path) -> None:
    _write_cli_plugin(tmp_path)
    tools = build_agent_tools(
        workspace_root=tmp_path,
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
    )
    tool = next(tool for tool in tools if tool.name == "echo_tool")

    result = asyncio.run(tool.execute("call-1", args=["hello"]))

    envelope = json.loads(result)
    stdout = json.loads(envelope["data"]["stdout"])
    assert envelope["success"] is True
    assert stdout["args"] == ["hello"]


def test_catalog_only_cli_plugin_is_not_exposed_directly(tmp_path: Path) -> None:
    _write_cli_plugin(tmp_path, exposure="catalog")

    assert "echo_tool" not in _tool_names(tmp_path)


def test_disabled_cli_plugin_is_not_exposed(tmp_path: Path) -> None:
    _write_cli_plugin(tmp_path, enabled=False)

    assert "echo_tool" not in _tool_names(tmp_path)


def test_workspace_plugin_hot_reload_appears_on_next_tool_build(tmp_path: Path) -> None:
    assert "echo_tool" not in _tool_names(tmp_path)

    _write_cli_plugin(tmp_path)

    assert "echo_tool" in _tool_names(tmp_path)
