"""Tests for plugin manifest discovery and source precedence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.plugins.discovery import PluginRoot, discover_plugins
from app.plugins.errors import PluginDiscoveryError


def _manifest_payload(plugin_id: str, *, overrides: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "id": plugin_id,
        "name": plugin_id.replace("_", " ").title(),
        "version": "1.0.0",
        "description": "Test plugin used by discovery tests.",
        "capabilities": [
            {
                "type": "settings",
                "id": "settings_capability",
                "title": "Settings",
                "description": "Settings metadata for this test plugin.",
            }
        ],
    }
    if overrides is not None:
        payload["overrides"] = overrides
    return payload


def _write_manifest(root: Path, plugin_id: str, *, overrides: str | None = None) -> Path:
    """Write a minimal valid plugin manifest under ``root``."""
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True)
    path = plugin_dir / "plugin.json"
    path.write_text(json.dumps(_manifest_payload(plugin_id, overrides=overrides)), encoding="utf-8")
    return path


def test_discovery_finds_bundled_global_and_workspace_roots(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    global_root = tmp_path / "global"
    workspace = tmp_path / "workspace"
    _write_manifest(bundled, "bundled_plugin")
    _write_manifest(global_root, "global_plugin")
    _write_manifest(workspace, "workspace_plugin")

    discovered = discover_plugins(
        (
            PluginRoot("bundled", bundled),
            PluginRoot("global", global_root),
            PluginRoot("workspace", workspace),
        )
    )

    assert [plugin.plugin_id for plugin in discovered] == [
        "bundled_plugin",
        "global_plugin",
        "workspace_plugin",
    ]
    assert all(plugin.fingerprint for plugin in discovered)


def test_discovery_requires_explicit_override_for_duplicate_ids(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    workspace = tmp_path / "workspace"
    _write_manifest(bundled, "same_plugin")
    _write_manifest(workspace, "same_plugin")

    with pytest.raises(PluginDiscoveryError, match="Duplicate plugin id"):
        discover_plugins((PluginRoot("bundled", bundled), PluginRoot("workspace", workspace)))


def test_discovery_allows_explicit_higher_precedence_override(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    workspace = tmp_path / "workspace"
    _write_manifest(bundled, "same_plugin")
    _write_manifest(workspace, "same_plugin", overrides="same_plugin")

    discovered = discover_plugins(
        (PluginRoot("bundled", bundled), PluginRoot("workspace", workspace))
    )

    assert len(discovered) == 1
    assert discovered[0].source_type == "workspace"


def test_manifest_changes_change_fingerprint(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    manifest_path = _write_manifest(root, "fingerprinted")
    first = discover_plugins((PluginRoot("bundled", root),))[0]
    payload = _manifest_payload("fingerprinted")
    payload["description"] = "Changed test plugin description for fingerprinting."
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    second = discover_plugins((PluginRoot("bundled", root),))[0]

    assert first.fingerprint != second.fingerprint


def test_undeclared_files_do_not_change_fingerprint(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    _write_manifest(root, "fingerprinted")
    first = discover_plugins((PluginRoot("bundled", root),))[0]
    (root / "fingerprinted" / "runtime.log").write_text("changed\n", encoding="utf-8")

    second = discover_plugins((PluginRoot("bundled", root),))[0]

    assert first.fingerprint == second.fingerprint


def test_invalid_manifest_remains_discoverable_as_failed_candidate(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    plugin_dir = root / "broken_plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text("{not json", encoding="utf-8")

    discovered = discover_plugins((PluginRoot("bundled", root),))

    assert discovered[0].plugin_id == "broken_plugin"
    assert discovered[0].manifest is None
    assert discovered[0].error
