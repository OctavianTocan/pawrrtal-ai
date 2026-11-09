"""paw plugins — local plugin platform inspection and control."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from app.cli.paw.commands.plugins_scaffold import scaffold_plugin
from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode
from app.plugins.capability_catalog import CapabilitySearch
from app.plugins.discovery import default_plugin_roots, discover_plugins
from app.plugins.fingerprints import fingerprint_plugin
from app.plugins.host import get_plugin_host
from app.plugins.manifest import PluginManifest, PluginSourceType, validate_plugin_manifest
from app.plugins.registry import ContributionRegistrySnapshot, build_registry_snapshot
from app.plugins.state import PluginState, load_plugin_state, plugin_state_path, save_plugin_state

app = typer.Typer(
    help="Inspect, validate, reload, and search dynamic Pawrrtal plugins.",
    no_args_is_help=True,
)
capabilities_app = typer.Typer(
    help="Search and describe plugin capabilities.", no_args_is_help=True
)
slots_app = typer.Typer(help="List and set capability slot preferences.", no_args_is_help=True)

app.add_typer(capabilities_app, name="capabilities", help="Search and describe capabilities.")
app.add_typer(slots_app, name="slots", help="List and prefer slot candidates.")
app.command("scaffold")(scaffold_plugin)


@app.command("spec")
def spec(json_out: bool = typer.Option(False, "--json")) -> None:
    """Print the plugin manifest schema.

    Examples:
      paw plugins spec
      paw plugins spec --json
    """
    schema = PluginManifest.model_json_schema()
    if json_out:
        emit_json(schema)
        return
    emit_human("Pawrrtal plugin manifest schema: schema_version=1, capabilities=[...]")


@app.command("validate")
def validate(
    path: Path = typer.Argument(..., help="Plugin directory or plugin.json path."),
    source: PluginSourceType = typer.Option("workspace", "--source"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Validate one plugin manifest and compute its fingerprint.

    Examples:
      paw plugins validate .agent/plugins/notion
      paw plugins validate backend/plugins/notion/plugin.json --source bundled --json
    """
    manifest_path = _manifest_path(path)
    try:
        manifest = validate_plugin_manifest(
            manifest_path.read_text(encoding="utf-8"),
            source_type=source,
        )
        fingerprint = fingerprint_plugin(manifest_path.parent, manifest)
    except Exception as exc:
        raise LocalError(
            f"Plugin manifest validation failed: {exc}",
            hint="Run `paw plugins spec --json` to inspect the manifest contract.",
        ) from exc
    payload = _manifest_summary(manifest, source_type=source, fingerprint=fingerprint)
    if json_out:
        emit_json(payload)
        return
    emit_human(f"valid plugin {manifest.id} ({source}); fingerprint {fingerprint[:12]}")


@app.command("list")
def list_plugins(
    workspace_root: Path | None = typer.Option(None, "--workspace-root"),
    pawrrtal_home: Path | None = typer.Option(None, "--pawrrtal-home"),
    include_unavailable: bool = typer.Option(False, "--include-unavailable"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List discovered plugins for one workspace snapshot.

    Examples:
      paw plugins list --workspace-root /data/workspaces/default
      paw plugins list --include-unavailable --json
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    snapshot = _snapshot(workspace_root=workspace_root, pawrrtal_home=pawrrtal_home)
    rows = [_outcome_wire(outcome) for outcome in snapshot.outcomes]
    if not include_unavailable:
        rows = [row for row in rows if row["status"] == "active"]
    _emit_rows(
        rows,
        json_out=json_out,
        plain=plain,
        columns=("plugin_id", "source_type", "status", "reason"),
    )


@app.command("enable")
def enable_plugin(
    plugin_id: str = typer.Argument(...),
    workspace_root: Path = typer.Option(..., "--workspace-root"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Enable one plugin for a workspace.

    Examples:
      paw plugins enable notion --workspace-root /data/workspaces/default
      paw plugins enable local_search --workspace-root ~/paw --json
    """
    state_path = plugin_state_path(
        plugin_id=plugin_id,
        scope="workspace",
        workspace_root=workspace_root,
    )
    state = _load_existing_workspace_state(state_path)
    next_state = _copy_state(state, enabled=True)
    save_plugin_state(state_path, next_state)
    payload = {"plugin_id": plugin_id, "enabled": True, "state_path": str(state_path)}
    if json_out:
        emit_json(payload)
        return
    emit_human(f"enabled plugin {plugin_id}")


@app.command("disable")
def disable_plugin(
    plugin_id: str = typer.Argument(...),
    workspace_root: Path = typer.Option(..., "--workspace-root"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Disable one plugin for a workspace.

    Examples:
      paw plugins disable notion --workspace-root /data/workspaces/default --yes
      paw plugins disable local_search --workspace-root ~/paw --yes --json
    """
    if not yes:
        raise LocalError(
            "Pass --yes to confirm disabling a plugin.",
            hint="paw plugins disable PLUGIN_ID --workspace-root PATH --yes",
        )
    state_path = plugin_state_path(
        plugin_id=plugin_id,
        scope="workspace",
        workspace_root=workspace_root,
    )
    state = _load_existing_workspace_state(state_path)
    next_state = _copy_state(state, enabled=False)
    save_plugin_state(state_path, next_state)
    payload = {"plugin_id": plugin_id, "enabled": False, "state_path": str(state_path)}
    if json_out:
        emit_json(payload)
        return
    emit_human(f"disabled plugin {plugin_id}")


@app.command("doctor")
def doctor(
    workspace_root: Path | None = typer.Option(None, "--workspace-root"),
    pawrrtal_home: Path | None = typer.Option(None, "--pawrrtal-home"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Diagnose plugin load outcomes for one workspace.

    Examples:
      paw plugins doctor --workspace-root /data/workspaces/default
      paw plugins doctor --json
    """
    snapshot = _snapshot(workspace_root=workspace_root, pawrrtal_home=pawrrtal_home)
    rows = [_outcome_wire(outcome) for outcome in snapshot.outcomes]
    passed = all(row["status"] in {"active", "disabled"} for row in rows)
    payload = {"passed": passed, "fingerprint": snapshot.fingerprint, "plugins": rows}
    if json_out:
        emit_json(payload)
        return
    for row in rows:
        emit_human(f"{row['plugin_id']}: {row['status']} {row['reason'] or ''}".rstrip())
    emit_human(f"{sum(row['status'] == 'active' for row in rows)}/{len(rows)} active.")
    if not passed:
        raise typer.Exit(code=6)


@app.command("graph")
def graph(
    workspace_root: Path | None = typer.Option(None, "--workspace-root"),
    pawrrtal_home: Path | None = typer.Option(None, "--pawrrtal-home"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Show plugin dependency edges for one workspace snapshot.

    Examples:
      paw plugins graph --workspace-root /data/workspaces/default
      paw plugins graph --plain
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    snapshot = _snapshot(workspace_root=workspace_root, pawrrtal_home=pawrrtal_home)
    rows = _graph_rows(snapshot)
    _emit_rows(rows, json_out=json_out, plain=plain, columns=("plugin_id", "depends_on", "status"))


@app.command("reload")
def reload_plugins(
    workspace_root: Path | None = typer.Option(None, "--workspace-root"),
    pawrrtal_home: Path | None = typer.Option(None, "--pawrrtal-home"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Reload and publish a workspace-keyed plugin snapshot in this process.

    Examples:
      paw plugins reload --workspace-root /data/workspaces/default
      paw plugins reload --json
    """
    previous, current = get_plugin_host().reload(
        workspace_root=workspace_root,
        pawrrtal_home=pawrrtal_home,
    )
    payload = {
        "workspace_key": current.workspace_key,
        "previous_fingerprint": previous.fingerprint,
        "fingerprint": current.fingerprint,
        "plugins": [_outcome_wire(outcome) for outcome in current.outcomes],
    }
    if json_out:
        emit_json(payload)
        return
    emit_human(f"reloaded plugins {previous.fingerprint[:12]} -> {current.fingerprint[:12]}")


@capabilities_app.command("search")
def capabilities_search(
    query: str | None = typer.Option(None, "--query", "-q"),
    capability_type: str | None = typer.Option(None, "--type"),
    intent: str | None = typer.Option(None, "--intent"),
    slot: str | None = typer.Option(None, "--slot"),
    tag: str | None = typer.Option(None, "--tag"),
    plugin_id: str | None = typer.Option(None, "--plugin"),
    permission: str | None = typer.Option(None, "--permission"),
    include_unavailable: bool = typer.Option(False, "--include-unavailable"),
    workspace_root: Path | None = typer.Option(None, "--workspace-root"),
    pawrrtal_home: Path | None = typer.Option(None, "--pawrrtal-home"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Search enabled plugin capabilities.

    Examples:
      paw plugins capabilities search --slot web_search
      paw plugins capabilities search --plugin notion --json
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    snapshot = _snapshot(workspace_root=workspace_root, pawrrtal_home=pawrrtal_home)
    filters = CapabilitySearch(
        query=query,
        capability_type=capability_type,
        intent=intent,
        slot=slot,
        tag=tag,
        plugin_id=plugin_id,
        permission=permission,
        include_unavailable=include_unavailable,
    )
    preferences = _slot_preferences(snapshot, slot) if slot else ()
    rows = [
        capability.to_wire(preferred=capability.key in preferences)
        for capability in snapshot.capability_catalog().search(
            filters,
            slot_preferences=preferences,
        )
    ]
    _emit_rows(
        rows,
        json_out=json_out,
        plain=plain,
        columns=("key", "type", "state", "title"),
    )


@slots_app.command("list")
def slots_list(
    workspace_root: Path | None = typer.Option(None, "--workspace-root"),
    pawrrtal_home: Path | None = typer.Option(None, "--pawrrtal-home"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List slots and candidates for one workspace snapshot.

    Examples:
      paw plugins slots list --workspace-root /data/workspaces/default
      paw plugins slots list --json
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    snapshot = _snapshot(workspace_root=workspace_root, pawrrtal_home=pawrrtal_home)
    rows = _slot_rows(snapshot)
    _emit_rows(rows, json_out=json_out, plain=plain, columns=("slot", "candidate", "state"))


@slots_app.command("prefer")
def slots_prefer(
    slot_id: str = typer.Argument(...),
    capability_key: str = typer.Argument(..., help="Composite key: plugin_id/capability_id."),
    workspace_root: Path = typer.Option(..., "--workspace-root"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Set one preferred capability for a slot in workspace plugin state.

    Examples:
      paw plugins slots prefer web_search exa_search/web_search --workspace-root ~/paw --yes
      paw plugins slots prefer web_search exa_search/web_search --workspace-root ~/paw --yes --json
    """
    if not yes:
        raise LocalError(
            "Pass --yes to confirm changing a slot preference.",
            hint="paw plugins slots prefer SLOT PLUGIN/CAPABILITY --workspace-root PATH --yes",
        )
    plugin_id, _, capability_id = capability_key.partition("/")
    if not plugin_id or not capability_id:
        raise LocalError("Capability key must be shaped as plugin_id/capability_id.")
    state_path = plugin_state_path(
        plugin_id=plugin_id,
        scope="workspace",
        workspace_root=workspace_root,
    )
    state = load_plugin_state(state_path, enabled_by_default=False, source_type="workspace")
    next_preferences = dict(state.slot_preferences)
    next_preferences[slot_id] = (capability_key,)
    next_state = PluginState(
        enabled=state.enabled,
        capabilities=state.capabilities,
        slot_preferences=next_preferences,
        validated_fingerprint=state.validated_fingerprint,
        validated_at=state.validated_at,
        last_validation=state.last_validation,
        failure_reason=state.failure_reason,
        doctor=state.doctor,
    )
    save_plugin_state(state_path, next_state)
    payload = {"slot": slot_id, "preferred": capability_key, "state_path": str(state_path)}
    if json_out:
        emit_json(payload)
        return
    emit_human(f"preferred {capability_key} for slot {slot_id}")


def _snapshot(
    *,
    workspace_root: Path | None,
    pawrrtal_home: Path | None,
) -> ContributionRegistrySnapshot:
    """Build a fresh local snapshot for CLI inspection."""
    roots = default_plugin_roots(workspace_root=workspace_root, pawrrtal_home=pawrrtal_home)
    discovered = discover_plugins(roots)
    return build_registry_snapshot(
        discovered,
        workspace_root=workspace_root,
        pawrrtal_home=pawrrtal_home,
    )


def _manifest_path(path: Path) -> Path:
    """Resolve a manifest path from a plugin dir or explicit plugin.json."""
    if path.is_dir():
        return path / "plugin.json"
    return path


def _manifest_summary(
    manifest: PluginManifest,
    *,
    source_type: PluginSourceType,
    fingerprint: str,
) -> dict[str, object]:
    """Return machine-readable manifest validation output."""
    return {
        "plugin_id": manifest.id,
        "name": manifest.name,
        "source_type": source_type,
        "version": manifest.version,
        "enabled_by_default": manifest.enabled_by_default,
        "fingerprint": fingerprint,
        "capabilities": [capability.id for capability in manifest.capabilities],
        "env_keys": [spec.name for spec in manifest.all_env_specs()],
    }


def _outcome_wire(outcome: Any) -> dict[str, object]:
    """Return machine-readable load outcome output."""
    return {
        "plugin_id": outcome.plugin_id,
        "source_type": outcome.source_type,
        "status": outcome.status,
        "reason": outcome.reason,
        "manifest_path": str(outcome.manifest_path),
        "fingerprint": outcome.fingerprint,
        "missing_env": list(outcome.missing_env),
        "capabilities": len(outcome.manifest.capabilities) if outcome.manifest else 0,
    }


def _graph_rows(snapshot: ContributionRegistrySnapshot) -> list[dict[str, object]]:
    """Return dependency graph rows."""
    rows: list[dict[str, object]] = []
    for outcome in snapshot.outcomes:
        if outcome.manifest is None:
            rows.append(
                {"plugin_id": outcome.plugin_id, "depends_on": "", "status": outcome.status}
            )
            continue
        dependencies = [dependency.id for dependency in outcome.manifest.depends_on]
        rows.append(
            {
                "plugin_id": outcome.plugin_id,
                "depends_on": ",".join(dependencies),
                "status": outcome.status,
            }
        )
    return rows


def _slot_rows(snapshot: ContributionRegistrySnapshot) -> list[dict[str, object]]:
    """Return one row per slot candidate."""
    rows: list[dict[str, object]] = []
    for capability in snapshot.capabilities:
        rows.extend(
            {"slot": slot, "candidate": capability.key, "state": capability.state}
            for slot in capability.slots
        )
    return rows


def _slot_preferences(
    snapshot: ContributionRegistrySnapshot,
    slot_id: str,
) -> tuple[str, ...]:
    """Collect ordered slot preferences from plugin state files."""
    preferences: list[str] = []
    for outcome in snapshot.outcomes:
        preferences.extend(outcome.state.slot_preference_keys(slot_id))
    return tuple(dict.fromkeys(preferences))


def _load_existing_workspace_state(state_path: Path) -> PluginState:
    """Load plugin state for workspace control commands."""
    return load_plugin_state(state_path, enabled_by_default=False, source_type="workspace")


def _copy_state(state: PluginState, *, enabled: bool) -> PluginState:
    """Copy a state file while changing only plugin enablement."""
    return PluginState(
        enabled=enabled,
        capabilities=state.capabilities,
        slot_preferences=state.slot_preferences,
        validated_fingerprint=state.validated_fingerprint,
        validated_at=state.validated_at,
        last_validation=state.last_validation,
        failure_reason=state.failure_reason,
        doctor=state.doctor,
    )


def _emit_rows(
    rows: list[dict[str, object]],
    *,
    json_out: bool,
    plain: bool,
    columns: tuple[str, ...],
) -> None:
    """Emit rows in the standard Paw output modes."""
    if json_out:
        emit_json(rows)
        return
    if plain:
        emit_plain_rows(tuple(row.get(column, "") for column in columns) for row in rows)
        return
    if not rows:
        emit_human("No rows.")
        return
    emit_human("  ".join(column.upper() for column in columns))
    for row in rows:
        emit_human("  ".join(str(row.get(column, "")) for column in columns))
