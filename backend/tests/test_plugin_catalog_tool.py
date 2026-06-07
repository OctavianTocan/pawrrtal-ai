"""Tests for the agent-facing plugin capability catalog tool."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import cast

from app.agents.tool_surface import build_agent_tools
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state
from app.tools.plugin_catalog import make_search_plugin_capabilities_tool


def _write_workspace_plugin(
    workspace_root: Path,
    *,
    plugin_id: str,
    capability_id: str,
    enabled: bool = True,
    priority: int = 0,
    slot_preferences: dict[str, tuple[str, ...]] | None = None,
) -> None:
    """Write a workspace CLI plugin and matching state."""
    plugin_dir = workspace_root / ".agent" / "plugins" / plugin_id
    plugin_dir.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "id": plugin_id,
        "name": plugin_id.replace("_", " ").title(),
        "version": "1.0.0",
        "description": "Workspace plugin used by the catalog search tool tests.",
        "permissions": ["subprocess"],
        "capabilities": [
            {
                "type": "cli_tool",
                "id": capability_id,
                "tool_name": capability_id,
                "title": capability_id.replace("_", " ").title(),
                "description": "Search capability used by the catalog search tool tests.",
                "slots": ["web_search"],
                "priority": priority,
                "entrypoint": ["echo"],
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
        PluginState(
            enabled=enabled,
            slot_preferences=slot_preferences or {},
        ),
    )


def _search(workspace_root: Path, **kwargs: object) -> dict[str, object]:
    """Execute the catalog tool and parse the JSON payload."""
    tool = make_search_plugin_capabilities_tool(workspace_root=workspace_root)
    payload = json.loads(asyncio.run(tool.execute("call-1", **kwargs)))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def test_search_plugin_capabilities_returns_enabled_slot_candidates(tmp_path: Path) -> None:
    _write_workspace_plugin(tmp_path, plugin_id="local_search", capability_id="web_search")

    payload = _search(tmp_path, slot="web_search")

    capabilities = payload["capabilities"]
    assert payload["success"] is True
    assert isinstance(capabilities, list)
    assert capabilities[0]["key"] == "local_search/web_search"
    assert capabilities[0]["state"] == "enabled"
    assert capabilities[0]["plugin_status"] == "active"


def test_search_plugin_capabilities_can_include_unavailable_rows(tmp_path: Path) -> None:
    _write_workspace_plugin(
        tmp_path,
        plugin_id="disabled_search",
        capability_id="web_search",
        enabled=False,
    )

    default_payload = _search(tmp_path, slot="web_search")
    unavailable_payload = _search(tmp_path, slot="web_search", include_unavailable=True)

    assert default_payload["capabilities"] == []
    capabilities = unavailable_payload["capabilities"]
    assert isinstance(capabilities, list)
    assert capabilities[0]["key"] == "disabled_search/web_search"
    assert capabilities[0]["state"] == "disabled"
    assert capabilities[0]["plugin_status"] == "disabled"


def test_search_plugin_capabilities_uses_slot_preferences(tmp_path: Path) -> None:
    _write_workspace_plugin(
        tmp_path,
        plugin_id="first_search",
        capability_id="web_search",
        priority=1,
        slot_preferences={"web_search": ("first_search/web_search",)},
    )
    _write_workspace_plugin(
        tmp_path,
        plugin_id="second_search",
        capability_id="web_search",
        priority=100,
    )

    payload = _search(tmp_path, slot="web_search")

    capabilities = payload["capabilities"]
    assert isinstance(capabilities, list)
    assert [capability["key"] for capability in capabilities] == [
        "first_search/web_search",
        "second_search/web_search",
    ]
    assert capabilities[0]["preferred"] is True


def test_agent_tool_surface_includes_plugin_capability_search(tmp_path: Path) -> None:
    tools = build_agent_tools(
        workspace_root=tmp_path,
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
    )

    assert "search_plugin_capabilities" in {tool.name for tool in tools}
