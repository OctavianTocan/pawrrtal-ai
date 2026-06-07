"""AgentTool adapters for plugin tool capabilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.types import AgentTool
from app.plugins.cli_runner import CliRunRequest, CliRunResult, run_cli_plugin
from app.plugins.contributions import CliToolCapability
from app.plugins.discovery import DiscoveredPlugin
from app.plugins.env import resolve_plugin_env
from app.plugins.registry import ContributionRegistrySnapshot


def build_snapshot_agent_tools(
    *,
    snapshot: ContributionRegistrySnapshot,
    workspace_root: Path,
) -> list[AgentTool]:
    """Build direct AgentTool objects from active CLI plugin capabilities."""
    discovered_by_id = {
        outcome.plugin_id: outcome for outcome in snapshot.outcomes if outcome.active
    }
    tools: list[AgentTool] = []
    for outcome in discovered_by_id.values():
        manifest = outcome.manifest
        if manifest is None:
            continue
        for capability in manifest.capabilities:
            if not isinstance(capability, CliToolCapability):
                continue
            if capability.exposure not in {"direct", "direct_and_catalog"}:
                continue
            if not outcome.state.is_capability_enabled(capability.id):
                continue
            tools.append(
                _build_cli_agent_tool(
                    plugin=DiscoveredPlugin(
                        plugin_id=outcome.plugin_id,
                        source_type=outcome.source_type,
                        plugin_dir=outcome.manifest_path.parent,
                        manifest_path=outcome.manifest_path,
                        manifest=manifest,
                        fingerprint=outcome.fingerprint,
                    ),
                    capability=capability,
                    workspace_root=workspace_root,
                )
            )
    return tools


def _build_cli_agent_tool(
    *,
    plugin: DiscoveredPlugin,
    capability: CliToolCapability,
    workspace_root: Path,
) -> AgentTool:
    """Build one AgentTool from a CLI capability."""
    manifest = plugin.manifest
    if manifest is None:
        raise ValueError("CLI AgentTool requires a valid plugin manifest")

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        args = _coerce_args(kwargs.get("args"))
        stdin = _coerce_stdin(kwargs.get("stdin"))
        result = await run_cli_plugin(
            CliRunRequest(
                argv=(*capability.entrypoint, *args),
                plugin_dir=plugin.plugin_dir,
                workspace_root=workspace_root,
                cwd_mode=capability.cwd,
                env=_materialize_env(workspace_root=workspace_root, plugin=plugin),
                stdin=stdin,
                timeout_seconds=capability.timeout_seconds,
                output_cap_bytes=capability.output_cap_bytes,
            )
        )
        payload = {
            "success": result.success,
            "content_items": _content_items(result),
            "data": result.to_data(),
            "error": None if result.success else _error_message(result),
            "operation_log_id": None,
        }
        return json.dumps(payload, ensure_ascii=False)

    return AgentTool(
        name=capability.tool_name,
        description=capability.description,
        parameters=capability.args_schema or _default_parameters(),
        execute=execute,
    )


def _materialize_env(*, workspace_root: Path, plugin: DiscoveredPlugin) -> dict[str, str]:
    """Resolve declared plugin env keys for subprocess injection."""
    manifest = plugin.manifest
    if manifest is None:
        return {}
    env: dict[str, str] = {}
    for spec in manifest.all_env_specs():
        resolution = resolve_plugin_env(workspace_root=workspace_root, spec=spec)
        if resolution.value is not None:
            env[resolution.inject_as] = resolution.value
    return env


def _coerce_args(value: object) -> tuple[str, ...]:
    """Coerce a tool-call ``args`` value into argv suffix strings."""
    if value is None:
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _coerce_stdin(value: object) -> str | None:
    """Coerce a tool-call ``stdin`` value."""
    if value is None:
        return None
    return str(value)


def _content_items(result: CliRunResult) -> list[dict[str, str]]:
    """Return bounded model-visible content items for a CLI result."""
    if result.stdout.strip():
        return [{"type": "text", "text": result.stdout}]
    if result.stderr.strip():
        return [{"type": "text", "text": result.stderr}]
    return [{"type": "text", "text": "CLI plugin completed."}]


def _error_message(result: CliRunResult) -> str:
    """Return a concise error string for failed CLI output."""
    if result.timed_out:
        return "CLI plugin timed out."
    if result.stderr.strip():
        return result.stderr.strip()
    return f"CLI plugin exited with return code {result.returncode}."


def _default_parameters() -> dict[str, Any]:
    """Return the default args/stdin schema for CLI plugin tools."""
    return {
        "type": "object",
        "properties": {
            "args": {"type": "array", "items": {"type": "string"}},
            "stdin": {"type": "string"},
        },
        "required": [],
        "additionalProperties": False,
    }
