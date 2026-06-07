"""Tests for manifest-backed plugin tools in agent tool composition."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

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


def test_bundled_github_issues_manifest_is_disabled_by_default(tmp_path: Path) -> None:
    assert "report_issue" not in _tool_names(tmp_path)


def test_bundled_github_issues_manifest_exposes_report_issue_when_configured(
    tmp_path: Path,
) -> None:
    save_workspace_env(tmp_path, {"GITHUB_TOKEN": "secret"})
    save_plugin_state(
        plugin_state_path(plugin_id="github_issues", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=True),
    )

    assert "report_issue" in _tool_names(tmp_path)


def test_bundled_github_issues_plugin_can_be_disabled(tmp_path: Path) -> None:
    save_workspace_env(tmp_path, {"GITHUB_TOKEN": "secret"})
    save_plugin_state(
        plugin_state_path(plugin_id="github_issues", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=False),
    )

    assert "report_issue" not in _tool_names(tmp_path)


def test_bundled_image_generation_manifest_is_disabled_by_default(tmp_path: Path) -> None:
    save_workspace_env(tmp_path, {"OPENAI_CODEX_OAUTH_TOKEN": "secret"})

    assert "generate_image" not in _tool_names(tmp_path)


def test_bundled_image_generation_requires_configuration_when_enabled(
    tmp_path: Path,
) -> None:
    save_plugin_state(
        plugin_state_path(plugin_id="image_generation", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=True),
    )

    assert "generate_image" not in _tool_names(tmp_path)


def test_bundled_image_generation_exposes_tool_when_enabled_and_configured(
    tmp_path: Path,
) -> None:
    save_workspace_env(tmp_path, {"OPENAI_CODEX_OAUTH_TOKEN": "secret"})
    save_plugin_state(
        plugin_state_path(plugin_id="image_generation", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=True),
    )

    assert "generate_image" in _tool_names(tmp_path)


def test_bundled_exa_search_manifest_is_disabled_by_default(tmp_path: Path) -> None:
    save_workspace_env(tmp_path, {"EXA_API_KEY": "secret"})

    assert "exa_search" not in _tool_names(tmp_path)


def test_bundled_exa_search_requires_configuration_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    save_plugin_state(
        plugin_state_path(plugin_id="exa_search", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=True),
    )

    assert "exa_search" not in _tool_names(tmp_path)


def test_bundled_exa_search_exposes_tool_when_enabled_and_configured(
    tmp_path: Path,
) -> None:
    save_workspace_env(tmp_path, {"EXA_API_KEY": "secret"})
    save_plugin_state(
        plugin_state_path(plugin_id="exa_search", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=True),
    )

    assert "exa_search" in _tool_names(tmp_path)


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


def test_bundled_document_conversion_exposes_markdown_tool(tmp_path: Path) -> None:
    assert "convert_to_markdown" in _tool_names(tmp_path)


def test_bundled_document_conversion_plugin_can_be_disabled(tmp_path: Path) -> None:
    save_plugin_state(
        plugin_state_path(
            plugin_id="document_conversion",
            scope="workspace",
            workspace_root=tmp_path,
        ),
        PluginState(enabled=False),
    )

    assert "convert_to_markdown" not in _tool_names(tmp_path)


def test_bundled_artifacts_plugin_exposes_render_tool(tmp_path: Path) -> None:
    assert "render_artifact" in _tool_names(tmp_path)


def test_bundled_artifacts_plugin_can_be_disabled(tmp_path: Path) -> None:
    save_plugin_state(
        plugin_state_path(plugin_id="artifacts", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=False),
    )

    assert "render_artifact" not in _tool_names(tmp_path)


def test_bundled_reminders_manifest_exposes_reminder_tools(tmp_path: Path) -> None:
    names = _tool_names(tmp_path)

    assert {"reminder_schedule", "reminder_list", "reminder_cancel"} <= names


def test_bundled_reminders_plugin_can_be_disabled(tmp_path: Path) -> None:
    save_plugin_state(
        plugin_state_path(plugin_id="reminders", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=False),
    )

    names = _tool_names(tmp_path)

    assert "reminder_schedule" not in names
    assert "reminder_list" not in names
    assert "reminder_cancel" not in names


def test_bundled_reminders_keep_conversation_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = AsyncMock()
    job_id = uuid.uuid4()
    row = MagicMock()
    row.id = job_id
    row.name = "daily standup"
    row.cron_expression = "0 9 * * 1-5"
    scheduler.add_job.return_value = row
    monkeypatch.setattr("app.tools.cron_tools.get_active_scheduler", lambda: scheduler)
    conversation_id = uuid.uuid4()
    tools = build_agent_tools(
        workspace_root=tmp_path,
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        conversation_id=conversation_id,
    )
    tool = next(item for item in tools if item.name == "reminder_schedule")

    result = asyncio.run(
        tool.execute(
            "call-1",
            name="daily standup",
            cron_expression="0 9 * * 1-5",
            prompt="Remind me",
        )
    )

    assert str(job_id) in result
    assert scheduler.add_job.await_args.kwargs["target_conversation_id"] == conversation_id


def test_bundled_skills_manifest_exposes_skill_tools(tmp_path: Path) -> None:
    names = _tool_names(tmp_path)

    assert {"list_skills", "read_skill", "invoke_skill"} <= names


def test_bundled_skills_plugin_can_be_disabled(tmp_path: Path) -> None:
    save_plugin_state(
        plugin_state_path(plugin_id="skills", scope="workspace", workspace_root=tmp_path),
        PluginState(enabled=False),
    )

    names = _tool_names(tmp_path)

    assert "list_skills" not in names
    assert "read_skill" not in names
    assert "invoke_skill" not in names


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
