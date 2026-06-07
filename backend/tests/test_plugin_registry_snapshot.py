"""Tests for immutable plugin registry snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from app.infrastructure.keys import save_workspace_env
from app.plugins.capability_catalog import CapabilitySearch
from app.plugins.discovery import PluginRoot, discover_plugins
from app.plugins.host import PluginHost
from app.plugins.registry import ContributionRegistrySnapshot, build_registry_snapshot
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state


def _write_tool_plugin(
    root: Path,
    plugin_id: str,
    capability_id: str,
    *,
    enabled_by_default: bool = True,
    required_env: bool = False,
    depends_on: tuple[str, ...] = (),
) -> None:
    """Write a plugin with one CLI tool capability."""
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True)
    payload: dict[str, object] = {
        "schema_version": 1,
        "id": plugin_id,
        "name": plugin_id.replace("_", " ").title(),
        "version": "1.0.0",
        "description": "Test plugin used by registry snapshot tests.",
        "enabled_by_default": enabled_by_default,
        "depends_on": [{"id": dependency} for dependency in depends_on],
        "permissions": ["subprocess"],
        "capabilities": [
            {
                "type": "cli_tool",
                "id": capability_id,
                "tool_name": capability_id,
                "title": "Tool",
                "description": "A tool capability used by snapshot tests.",
                "slots": ["web_search"],
                "entrypoint": ["tool"],
            }
        ],
    }
    if required_env:
        payload["env"] = [
            {
                "name": "SNAPSHOT_API_KEY",
                "required": True,
                "scope": "workspace",
                "overridable": True,
                "gateway_fallback": False,
                "secret": True,
                "label": "Snapshot API Key",
            }
        ]
    (plugin_dir / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")


def test_empty_snapshot_is_valid() -> None:
    snapshot = ContributionRegistrySnapshot.empty(workspace_key="test")

    assert snapshot.workspace_key == "test"
    assert snapshot.outcomes == ()
    assert snapshot.capabilities == ()
    assert snapshot.fingerprint


def test_snapshot_includes_active_bundled_default_capabilities(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    workspace = tmp_path / "workspace"
    _write_tool_plugin(root, "search_pack", "web_search")
    discovered = discover_plugins((PluginRoot("bundled", root),))

    snapshot = build_registry_snapshot(discovered, workspace_root=workspace)

    assert [outcome.status for outcome in snapshot.outcomes] == ["active"]
    assert [capability.key for capability in snapshot.capabilities] == ["search_pack/web_search"]


def test_workspace_state_can_disable_bundled_plugin(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    workspace = tmp_path / "workspace"
    _write_tool_plugin(root, "search_pack", "web_search")
    state_path = plugin_state_path(
        plugin_id="search_pack",
        scope="workspace",
        workspace_root=workspace,
    )
    save_plugin_state(state_path, PluginState(enabled=False))
    discovered = discover_plugins((PluginRoot("bundled", root),))

    snapshot = build_registry_snapshot(discovered, workspace_root=workspace)

    assert snapshot.outcomes[0].status == "disabled"
    assert snapshot.capabilities[0].state == "disabled"
    assert snapshot.capability_catalog().search(CapabilitySearch(slot="web_search")) == ()
    assert snapshot.capability_catalog().search(
        CapabilitySearch(slot="web_search", include_unavailable=True)
    )


def test_stale_validation_fingerprint_marks_plugin_needs_validation(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    workspace = tmp_path / "workspace"
    _write_tool_plugin(root, "search_pack", "web_search")
    state_path = plugin_state_path(
        plugin_id="search_pack",
        scope="workspace",
        workspace_root=workspace,
    )
    save_plugin_state(
        state_path,
        PluginState(
            enabled=True,
            validated_fingerprint="old",
        ),
    )
    discovered = discover_plugins((PluginRoot("bundled", root),))

    snapshot = build_registry_snapshot(discovered, workspace_root=workspace)

    assert snapshot.outcomes[0].status == "needs_validation"
    assert snapshot.capabilities[0].state == "needs_validation"


def test_missing_required_env_marks_plugin_misconfigured(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    workspace = tmp_path / "workspace"
    _write_tool_plugin(root, "search_pack", "web_search", required_env=True)
    discovered = discover_plugins((PluginRoot("bundled", root),))

    snapshot = build_registry_snapshot(discovered, workspace_root=workspace)

    assert snapshot.outcomes[0].status == "misconfigured"
    assert snapshot.outcomes[0].missing_env == ("SNAPSHOT_API_KEY",)
    assert snapshot.capabilities[0].state == "misconfigured"


def test_workspace_env_configures_required_plugin(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    workspace = tmp_path / "workspace"
    _write_tool_plugin(root, "search_pack", "web_search", required_env=True)
    save_workspace_env(workspace, {"SNAPSHOT_API_KEY": "configured"})
    discovered = discover_plugins((PluginRoot("bundled", root),))

    snapshot = build_registry_snapshot(discovered, workspace_root=workspace)

    assert snapshot.outcomes[0].status == "active"
    assert snapshot.capabilities[0].state == "enabled"


def test_disabled_dependency_blocks_dependent_plugin(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    workspace = tmp_path / "workspace"
    _write_tool_plugin(root, "base_plugin", "base_tool", enabled_by_default=False)
    _write_tool_plugin(root, "child_plugin", "child_tool", depends_on=("base_plugin",))
    discovered = discover_plugins((PluginRoot("bundled", root),))

    snapshot = build_registry_snapshot(discovered, workspace_root=workspace)

    base = snapshot.outcome_for("base_plugin")
    child = snapshot.outcome_for("child_plugin")
    assert base is not None
    assert child is not None
    assert base.status == "disabled"
    assert child.status == "blocked_by_dependency"


def test_failed_plugin_remains_inspectable(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    plugin_dir = root / "broken_plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text("{not json", encoding="utf-8")
    discovered = discover_plugins((PluginRoot("bundled", root),))

    snapshot = build_registry_snapshot(discovered, workspace_root=tmp_path / "workspace")

    assert snapshot.outcomes[0].status == "failed"
    assert snapshot.outcomes[0].reason


def test_snapshot_fingerprint_changes_when_active_capabilities_change(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    workspace = tmp_path / "workspace"
    _write_tool_plugin(root, "search_pack", "web_search")
    discovered = discover_plugins((PluginRoot("bundled", root),))
    first = build_registry_snapshot(discovered, workspace_root=workspace)
    _write_tool_plugin(root, "search_pack_two", "web_search_two")
    discovered_again = discover_plugins((PluginRoot("bundled", root),))

    second = build_registry_snapshot(discovered_again, workspace_root=workspace)

    assert first.fingerprint != second.fingerprint


def test_plugin_host_swaps_workspace_snapshots_without_cross_workspace_leak(
    tmp_path: Path,
) -> None:
    host = PluginHost()
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    plugin_root = workspace_a / ".agent" / "plugins"
    _write_tool_plugin(
        plugin_root,
        "workspace_tool",
        "workspace_capability",
        enabled_by_default=False,
    )
    state_path = plugin_state_path(
        plugin_id="workspace_tool",
        scope="workspace",
        workspace_root=workspace_a,
    )
    save_plugin_state(state_path, PluginState(enabled=True))

    previous_a, next_a = host.reload(workspace_root=workspace_a, pawrrtal_home=tmp_path)

    assert previous_a.capabilities == ()
    assert next_a is host.snapshot(workspace_root=workspace_a)
    assert host.snapshot(workspace_root=workspace_b).capabilities == ()
