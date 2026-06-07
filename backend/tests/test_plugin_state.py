"""Tests for persisted plugin state."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.plugins.state import (
    CapabilityState,
    PluginState,
    load_plugin_state,
    plugin_state_path,
    save_plugin_state,
)


def test_default_state_enables_only_bundled_defaults(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    enabled = load_plugin_state(path, enabled_by_default=True, source_type="bundled")
    disabled_global = load_plugin_state(path, enabled_by_default=True, source_type="global")
    disabled_workspace = load_plugin_state(path, enabled_by_default=True, source_type="workspace")

    assert enabled.enabled is True
    assert disabled_global.enabled is False
    assert disabled_workspace.enabled is False


def test_state_round_trips_atomically(tmp_path: Path) -> None:
    path = tmp_path / "plugin-state" / "alpha.json"
    state = PluginState(
        enabled=True,
        capabilities={"alpha_tool": CapabilityState(enabled=False)},
        slot_preferences={"web_search": ("alpha/web_search",)},
        validated_fingerprint="abc",
    )

    save_plugin_state(path, state)
    loaded = load_plugin_state(path, enabled_by_default=False, source_type="bundled")

    assert loaded == state
    assert loaded.slot_preference_keys("web_search") == ("alpha/web_search",)
    assert not (tmp_path / "plugin-state" / "alpha.json.tmp").exists()


def test_loaded_state_nested_maps_are_immutable(tmp_path: Path) -> None:
    state = PluginState(
        enabled=True,
        capabilities={"alpha_tool": CapabilityState(enabled=True)},
        slot_preferences={"web_search": ("alpha/web_search",)},
    )

    with pytest.raises(TypeError):
        state.capabilities["other"] = CapabilityState(enabled=True)  # type: ignore[index]
    with pytest.raises(TypeError):
        state.slot_preferences["web_search"] = ("other/web_search",)  # type: ignore[index]


def test_plugin_state_path_uses_workspace_agent_dir(tmp_path: Path) -> None:
    path = plugin_state_path(
        plugin_id="alpha",
        scope="workspace",
        workspace_root=tmp_path,
    )

    assert path == tmp_path / ".agent" / "plugin-state" / "alpha.json"


def test_plugin_state_path_keeps_global_scope_separate(tmp_path: Path) -> None:
    path = plugin_state_path(
        plugin_id="alpha",
        scope="global",
        pawrrtal_home=tmp_path,
    )

    assert path == tmp_path / "plugin-state" / "alpha.json"
