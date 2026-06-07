"""Tests for manifest-backed turn context providers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.plugins.adapters.turn_context import build_turn_context_providers
from app.plugins.discovery import PluginRoot, discover_plugins
from app.plugins.registry import build_registry_snapshot
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state


def test_bundled_active_recall_manifest_builds_provider_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active Recall is a bundled default context provider."""
    monkeypatch.setenv("PAWRRTAL_HOME", str(tmp_path / "home"))

    providers = build_turn_context_providers(workspace_root=tmp_path)

    active_recall = next(
        provider for provider in providers if provider.plugin_id == "active_recall"
    )
    assert active_recall.capability_id == "active_recall"
    assert active_recall.timeout_seconds == 10
    assert active_recall.provider.__name__ == "run_active_recall"


def test_turn_context_provider_hot_reload_respects_workspace_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workspace state can disable a bundled provider on the next reload."""
    monkeypatch.setenv("PAWRRTAL_HOME", str(tmp_path / "home"))
    assert any(
        provider.plugin_id == "active_recall"
        for provider in build_turn_context_providers(workspace_root=tmp_path)
    )
    save_plugin_state(
        plugin_state_path(
            plugin_id="active_recall",
            scope="workspace",
            workspace_root=tmp_path,
        ),
        PluginState(enabled=False),
    )

    providers = build_turn_context_providers(workspace_root=tmp_path)

    assert all(provider.plugin_id != "active_recall" for provider in providers)


def test_workspace_plugins_cannot_register_turn_context_provider(tmp_path: Path) -> None:
    """Workspace plugins cannot load trusted Python lifecycle adapters."""
    plugin_dir = tmp_path / ".agent" / "plugins" / "workspace_recall"
    plugin_dir.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "id": "workspace_recall",
        "name": "Workspace Recall",
        "description": "Workspace plugin that should not load trusted Python.",
        "version": "1.0.0",
        "enabled_by_default": True,
        "capabilities": [
            {
                "type": "turn_context_provider",
                "id": "workspace_recall",
                "title": "Workspace Recall",
                "description": "Attempt to provide trusted Python context from a workspace.",
                "entrypoint": "workspace_recall.provider:run",
            }
        ],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")
    discovered = discover_plugins((PluginRoot("workspace", tmp_path / ".agent" / "plugins"),))

    snapshot = build_registry_snapshot(discovered, workspace_root=tmp_path)

    assert snapshot.outcomes[0].status == "failed"
    assert snapshot.outcomes[0].reason
