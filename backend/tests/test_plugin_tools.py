"""Tests for manifest-backed plugin tools in agent tool composition."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from app.agents.tool_surface import build_agent_tools
from app.infrastructure.keys import save_workspace_env
from app.plugins.adapters.tools import build_snapshot_agent_tools
from app.plugins.discovery import PluginRoot, discover_plugins
from app.plugins.registry import build_registry_snapshot
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state
from app.plugins.tool_context import ToolContext


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


def _write_python_tool_plugin(root: Path) -> None:
    """Write a non-bundled Python tool plugin for trust-boundary tests."""
    plugin_dir = root / "global_tasks"
    plugin_dir.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "id": "global_tasks",
        "name": "Global Tasks",
        "version": "1.0.0",
        "enabled_by_default": True,
        "description": "Global Python plugin that must not be imported by runtime tests.",
        "permissions": ["filesystem_write"],
        "capabilities": [
            {
                "type": "python_tool",
                "id": "global_add_task",
                "tool_name": "add_task",
                "title": "Global Add Task",
                "description": "Attempt to expose a Python task tool from a global plugin.",
                "exposure": "direct_and_catalog",
                "permissions": ["filesystem_write"],
                "entrypoint": "app.plugins.tasks.tools:make_add_task_tool",
            }
        ],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")


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


def test_bundled_notion_manifest_exposes_tool_when_enabled_and_configured(
    tmp_path: Path,
) -> None:
    save_workspace_env(tmp_path, {"NOTION_API_KEY": "secret"})
    save_plugin_state(
        plugin_state_path(plugin_id="notion", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=True),
    )

    assert "notion_cli" in _tool_names(tmp_path)


def test_bundled_tasks_manifest_exposes_task_tools(tmp_path: Path) -> None:
    names = _tool_names(tmp_path)

    assert {"add_task", "list_tasks", "complete_task"} <= names


def test_bundled_tasks_plugin_can_be_disabled(tmp_path: Path) -> None:
    save_plugin_state(
        plugin_state_path(plugin_id="tasks", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=False),
    )

    names = _tool_names(tmp_path)

    assert "add_task" not in names
    assert "list_tasks" not in names
    assert "complete_task" not in names


def test_non_bundled_python_tool_manifest_is_not_imported(tmp_path: Path) -> None:
    global_root = tmp_path / "global-plugins"
    workspace_root = tmp_path / "workspace"
    _write_python_tool_plugin(global_root)
    discovered = discover_plugins((PluginRoot("global", global_root),))
    snapshot = build_registry_snapshot(discovered, workspace_root=workspace_root)

    tools = build_snapshot_agent_tools(
        snapshot=snapshot,
        workspace_root=workspace_root,
        tool_context=ToolContext(
            workspace_id=uuid.uuid4(),
            workspace_root=workspace_root,
            user_id=uuid.uuid4(),
        ),
    )

    assert "add_task" not in {tool.name for tool in tools}
