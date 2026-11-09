"""Tests for ``paw plugins scaffold``."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli.paw.main import app


def test_plugins_scaffold_creates_enabled_workspace_cli_plugin(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "plugins",
            "scaffold",
            "local_notes",
            "--tool-name",
            "search_notes",
            "--workspace-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    plugin_dir = Path(payload["plugin_dir"])
    assert plugin_dir.joinpath("plugin.json").is_file()
    assert plugin_dir.joinpath("search_notes.py").is_file()
    assert Path(payload["state_path"]).is_file()
    assert payload["enabled"] is True

    validate = runner.invoke(
        app,
        ["plugins", "validate", str(plugin_dir), "--json"],
    )
    assert validate.exit_code == 0, validate.stdout
    assert json.loads(validate.stdout)["plugin_id"] == "local_notes"

    search = runner.invoke(
        app,
        [
            "plugins",
            "capabilities",
            "search",
            "--workspace-root",
            str(tmp_path),
            "--plugin",
            "local_notes",
            "--json",
        ],
    )
    assert search.exit_code == 0, search.stdout
    rows = json.loads(search.stdout)
    assert rows[0]["key"] == "local_notes/search_notes"
    assert rows[0]["state"] == "enabled"
    assert rows[0]["exposure"] == "catalog"
    assert rows[0]["invokable"] is False


def test_plugins_scaffold_refuses_existing_plugin_dir(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / ".agent" / "plugins" / "local_notes"
    plugin_dir.mkdir(parents=True)

    result = runner.invoke(
        app,
        [
            "plugins",
            "scaffold",
            "local_notes",
            "--workspace-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert not plugin_dir.joinpath("plugin.json").exists()
