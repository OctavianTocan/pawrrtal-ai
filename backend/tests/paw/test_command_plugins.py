"""Tests for ``paw plugins`` local plugin-management commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli.paw.main import app
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state


def _write_workspace_plugin(
    workspace_root: Path,
    plugin_id: str = "local_search",
    *,
    capability_id: str = "web_search",
    priority: int = 10,
    enabled: bool = True,
) -> Path:
    """Create a workspace plugin fixture and enable it in state."""
    plugin_dir = workspace_root / ".agent" / "plugins" / plugin_id
    plugin_dir.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "id": plugin_id,
        "name": plugin_id.replace("_", " ").title(),
        "version": "1.0.0",
        "description": "Local search plugin used by Paw CLI tests.",
        "enabled_by_default": False,
        "permissions": ["subprocess"],
        "capabilities": [
            {
                "type": "cli_tool",
                "id": capability_id,
                "tool_name": capability_id,
                "title": "Web Search",
                "description": "Search the web through a local workspace CLI.",
                "slots": ["web_search"],
                "tags": ["search"],
                "priority": priority,
                "entrypoint": ["search-cli"],
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
    return plugin_dir


def test_plugins_spec_returns_manifest_schema_json(runner: CliRunner) -> None:
    result = runner.invoke(app, ["plugins", "spec", "--json"])

    assert result.exit_code == 0, result.stdout
    schema = json.loads(result.stdout)
    assert schema["properties"]["schema_version"]["const"] == 1
    assert "capabilities" in schema["properties"]


def test_plugins_validate_accepts_workspace_cli_plugin(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    plugin_dir = _write_workspace_plugin(tmp_path)

    result = runner.invoke(app, ["plugins", "validate", str(plugin_dir), "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["plugin_id"] == "local_search"
    assert payload["capabilities"] == ["web_search"]
    assert payload["fingerprint"]


def test_plugins_validate_rejects_workspace_provider_plugin(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / ".agent" / "plugins" / "bad_provider"
    plugin_dir.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "id": "bad_provider",
        "name": "Bad Provider",
        "version": "1.0.0",
        "description": "Provider plugin that should not be workspace safe.",
        "capabilities": [
            {
                "type": "provider",
                "id": "bad_provider",
                "description": "Provider capability that imports Python runtime code.",
                "entrypoint": "app.providers.bad:create_provider",
            }
        ],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(app, ["plugins", "validate", str(plugin_dir)])

    assert result.exit_code == 1


def test_plugins_reload_returns_workspace_snapshot(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    _write_workspace_plugin(tmp_path)

    result = runner.invoke(app, ["plugins", "reload", "--workspace-root", str(tmp_path), "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["workspace_key"] == str(tmp_path.resolve())
    assert payload["plugins"][0]["status"] == "active"


def test_plugins_enable_activates_workspace_plugin(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    _write_workspace_plugin(tmp_path, enabled=False)

    result = runner.invoke(
        app,
        ["plugins", "enable", "local_search", "--workspace-root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["enabled"] is True
    listed = runner.invoke(
        app,
        ["plugins", "list", "--workspace-root", str(tmp_path), "--json"],
    )
    assert json.loads(listed.stdout)[0]["status"] == "active"


def test_plugins_disable_requires_confirmation(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    _write_workspace_plugin(tmp_path)

    result = runner.invoke(
        app,
        ["plugins", "disable", "local_search", "--workspace-root", str(tmp_path)],
    )

    assert result.exit_code == 1


def test_plugins_disable_deactivates_workspace_plugin(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    _write_workspace_plugin(tmp_path)

    result = runner.invoke(
        app,
        [
            "plugins",
            "disable",
            "local_search",
            "--workspace-root",
            str(tmp_path),
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["enabled"] is False
    listed = runner.invoke(
        app,
        [
            "plugins",
            "list",
            "--workspace-root",
            str(tmp_path),
            "--include-unavailable",
            "--json",
        ],
    )
    assert json.loads(listed.stdout)[0]["status"] == "disabled"


def test_plugins_capabilities_search_filters_enabled_slot(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    _write_workspace_plugin(tmp_path)

    result = runner.invoke(
        app,
        [
            "plugins",
            "capabilities",
            "search",
            "--workspace-root",
            str(tmp_path),
            "--slot",
            "web_search",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert rows[0]["key"] == "local_search/web_search"
    assert rows[0]["state"] == "enabled"


def test_plugins_slots_prefer_requires_confirmation(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    _write_workspace_plugin(tmp_path)

    result = runner.invoke(
        app,
        [
            "plugins",
            "slots",
            "prefer",
            "web_search",
            "local_search/web_search",
            "--workspace-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1


def test_plugins_slots_prefer_affects_capability_search_order(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    _write_workspace_plugin(
        tmp_path, plugin_id="first_search", capability_id="web_search", priority=1
    )
    _write_workspace_plugin(
        tmp_path,
        plugin_id="second_search",
        capability_id="web_search",
        priority=100,
    )
    prefer = runner.invoke(
        app,
        [
            "plugins",
            "slots",
            "prefer",
            "web_search",
            "first_search/web_search",
            "--workspace-root",
            str(tmp_path),
            "--yes",
            "--json",
        ],
    )
    assert prefer.exit_code == 0, prefer.stdout

    result = runner.invoke(
        app,
        [
            "plugins",
            "capabilities",
            "search",
            "--workspace-root",
            str(tmp_path),
            "--slot",
            "web_search",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert [row["key"] for row in rows] == [
        "first_search/web_search",
        "second_search/web_search",
    ]
    assert rows[0]["preferred"] is True
