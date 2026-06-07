"""Plugin scaffold command for the Paw CLI."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json
from app.plugins.contributions import validate_capability_id, validate_identifier
from app.plugins.fingerprints import fingerprint_plugin
from app.plugins.manifest import validate_plugin_manifest
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state


def scaffold_plugin(
    plugin_id: str = typer.Argument(..., help="Lowercase plugin id, e.g. local_search."),
    workspace_root: Path = typer.Option(..., "--workspace-root"),
    tool_name: str | None = typer.Option(None, "--tool-name"),
    enable: bool = typer.Option(True, "--enable/--no-enable"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Create a workspace CLI plugin scaffold.

    Examples:
      paw plugins scaffold local_search --workspace-root ~/paw
      paw plugins scaffold local_search --tool-name search_notes --workspace-root ~/paw --json
    """
    plugin_id = _plugin_id(plugin_id)
    capability_id = _capability_id(tool_name or plugin_id)
    plugin_dir = workspace_root / ".agent" / "plugins" / plugin_id
    if plugin_dir.exists():
        raise LocalError(
            f"Plugin directory already exists: {plugin_dir}",
            hint="Pick a new plugin id or remove the existing scaffold yourself.",
        )

    manifest = _manifest(plugin_id=plugin_id, capability_id=capability_id)
    validate_plugin_manifest(manifest, source_type="workspace")
    plugin_dir.mkdir(parents=True)
    tool_path = plugin_dir / f"{capability_id}.py"
    manifest_path = plugin_dir / "plugin.json"
    tool_path.write_text(_tool_script(capability_id), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(manifest, indent="\t", sort_keys=False) + "\n",
        encoding="utf-8",
    )
    fingerprint = fingerprint_plugin(
        plugin_dir, validate_plugin_manifest(manifest, source_type="workspace")
    )
    state_path = plugin_state_path(
        plugin_id=plugin_id,
        scope="workspace",
        workspace_root=workspace_root,
    )
    if enable:
        save_plugin_state(state_path, PluginState(enabled=True))
    payload = {
        "plugin_id": plugin_id,
        "capability_id": capability_id,
        "plugin_dir": str(plugin_dir),
        "manifest_path": str(manifest_path),
        "tool_path": str(tool_path),
        "state_path": str(state_path),
        "enabled": enable,
        "fingerprint": fingerprint,
    }
    if json_out:
        emit_json(payload)
        return
    emit_human(f"created workspace plugin {plugin_id} at {plugin_dir}")


def _plugin_id(value: str) -> str:
    """Validate a plugin id for scaffold output."""
    try:
        return validate_identifier(value, field_name="plugin_id")
    except ValueError as exc:
        raise LocalError(str(exc)) from exc


def _capability_id(value: str) -> str:
    """Validate a capability/tool id for scaffold output."""
    try:
        return validate_capability_id(value, field_name="tool_name")
    except ValueError as exc:
        raise LocalError(str(exc)) from exc


def _manifest(*, plugin_id: str, capability_id: str) -> dict[str, object]:
    """Return a minimal workspace-safe CLI plugin manifest."""
    title = capability_id.replace("_", " ").title()
    return {
        "schema_version": 1,
        "id": plugin_id,
        "name": plugin_id.replace("_", " ").title(),
        "description": f"Workspace CLI plugin scaffold for {title}.",
        "version": "1.0.0",
        "permissions": ["subprocess"],
        "capabilities": [
            {
                "type": "cli_tool",
                "id": capability_id,
                "tool_name": capability_id,
                "title": title,
                "description": f"Run the {title} workspace CLI scaffold.",
                "exposure": "direct_and_catalog",
                "permissions": ["subprocess"],
                "entrypoint": ["python3", f"{capability_id}.py"],
                "cwd": "plugin",
                "args_schema": {
                    "type": "object",
                    "properties": {
                        "args": {"type": "array", "items": {"type": "string"}},
                        "stdin": {"type": "string"},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            }
        ],
    }


def _tool_script(capability_id: str) -> str:
    """Return the default CLI tool body."""
    return f'''#!/usr/bin/env python3
"""CLI scaffold for the {capability_id} Pawrrtal plugin."""

from __future__ import annotations

import json
import sys


def main() -> None:
    """Echo the invocation so the scaffold is immediately testable."""
    payload = {{
        "tool": "{capability_id}",
        "args": sys.argv[1:],
        "stdin": sys.stdin.read(),
    }}
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
'''
