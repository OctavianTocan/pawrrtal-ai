"""Immutable plugin registry snapshots for runtime composition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from app.plugins.capability_catalog import (
    CapabilityCatalog,
    CapabilityRecord,
    CapabilityState,
)
from app.plugins.contributions import Capability
from app.plugins.discovery import DiscoveredPlugin, default_pawrrtal_home
from app.plugins.env import plugin_env_status
from app.plugins.manifest import PluginManifest, PluginSourceType
from app.plugins.state import PluginState, load_plugin_state, plugin_state_path

PluginLoadStatus = Literal[
    "active",
    "disabled",
    "needs_validation",
    "misconfigured",
    "failed",
    "blocked_by_dependency",
]


@dataclass(frozen=True, slots=True)
class PluginLoadOutcome:
    """Inspectable load result for one plugin."""

    plugin_id: str
    source_type: PluginSourceType
    manifest_path: Path
    status: PluginLoadStatus
    reason: str | None
    fingerprint: str | None
    state: PluginState
    manifest: PluginManifest | None
    missing_env: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        """Return whether this plugin contributes enabled runtime capabilities."""
        return self.status == "active"


@dataclass(frozen=True, slots=True)
class ContributionRegistrySnapshot:
    """Immutable plugin contribution registry snapshot."""

    workspace_key: str
    outcomes: tuple[PluginLoadOutcome, ...]
    capabilities: tuple[CapabilityRecord, ...]
    fingerprint: str

    @classmethod
    def empty(cls, *, workspace_key: str = "global") -> ContributionRegistrySnapshot:
        """Return an empty valid snapshot for host boot."""
        return cls(
            workspace_key=workspace_key,
            outcomes=(),
            capabilities=(),
            fingerprint=_hash_payload({"workspace_key": workspace_key, "outcomes": []}),
        )

    def active_manifests(self) -> tuple[PluginManifest, ...]:
        """Return active manifests in snapshot order."""
        return tuple(
            outcome.manifest for outcome in self.outcomes if outcome.active and outcome.manifest
        )

    def capabilities_by_type(self, capability_type: str) -> tuple[Capability, ...]:
        """Return active manifest capabilities by type."""
        capabilities: list[Capability] = []
        for manifest in self.active_manifests():
            capabilities.extend(
                capability
                for capability in manifest.capabilities
                if capability.type == capability_type
            )
        return tuple(capabilities)

    def capability_catalog(self) -> CapabilityCatalog:
        """Return a catalog over this snapshot's capabilities."""
        return CapabilityCatalog(capabilities=self.capabilities)

    def outcome_for(self, plugin_id: str) -> PluginLoadOutcome | None:
        """Return the load outcome for one plugin id."""
        for outcome in self.outcomes:
            if outcome.plugin_id == plugin_id:
                return outcome
        return None


def build_registry_snapshot(
    discovered: tuple[DiscoveredPlugin, ...],
    *,
    workspace_root: Path | None = None,
    pawrrtal_home: Path | None = None,
) -> ContributionRegistrySnapshot:
    """Build a new immutable snapshot from discovered plugins and state."""
    workspace_key = _workspace_key(workspace_root)
    initial_outcomes = tuple(
        _load_outcome(
            plugin=plugin,
            workspace_root=workspace_root,
            pawrrtal_home=pawrrtal_home,
        )
        for plugin in discovered
    )
    outcomes = _apply_dependency_status(initial_outcomes)
    capabilities = _catalog_capabilities(outcomes)
    return ContributionRegistrySnapshot(
        workspace_key=workspace_key,
        outcomes=outcomes,
        capabilities=capabilities,
        fingerprint=_snapshot_fingerprint(workspace_key, outcomes, capabilities),
    )


def _load_outcome(
    *,
    plugin: DiscoveredPlugin,
    workspace_root: Path | None,
    pawrrtal_home: Path | None,
) -> PluginLoadOutcome:
    """Load state and turn one discovered manifest into a snapshot outcome."""
    if plugin.manifest is None:
        return _failed_outcome(plugin)

    state_path = _state_path_for_plugin(
        plugin_id=plugin.manifest.id,
        workspace_root=workspace_root,
        pawrrtal_home=pawrrtal_home,
    )
    state = load_plugin_state(
        state_path,
        enabled_by_default=plugin.manifest.enabled_by_default,
        source_type=plugin.source_type,
    )
    if not state.enabled:
        return _outcome(plugin=plugin, state=state, status="disabled", reason="Plugin disabled.")

    if state.validated_fingerprint and state.validated_fingerprint != plugin.fingerprint:
        return _outcome(
            plugin=plugin,
            state=state,
            status="needs_validation",
            reason="Validation fingerprint is stale.",
        )

    env_status = plugin_env_status(workspace_root=workspace_root, manifest=plugin.manifest)
    if not env_status.configured:
        return _outcome(
            plugin=plugin,
            state=state,
            status="misconfigured",
            reason=f"Missing required env keys: {', '.join(env_status.missing_required)}.",
            missing_env=env_status.missing_required,
        )

    return _outcome(plugin=plugin, state=state, status="active", reason=None)


def _failed_outcome(plugin: DiscoveredPlugin) -> PluginLoadOutcome:
    """Return an inspectable outcome for an invalid plugin."""
    return PluginLoadOutcome(
        plugin_id=plugin.plugin_id,
        source_type=plugin.source_type,
        manifest_path=plugin.manifest_path,
        status="failed",
        reason=plugin.error or "Plugin failed during discovery.",
        fingerprint=plugin.fingerprint,
        state=PluginState(enabled=False, failure_reason=plugin.error),
        manifest=None,
    )


def _state_path_for_plugin(
    *,
    plugin_id: str,
    workspace_root: Path | None,
    pawrrtal_home: Path | None,
) -> Path:
    """Return the state file path for a plugin in the active scope."""
    if workspace_root is not None:
        return plugin_state_path(
            plugin_id=plugin_id,
            scope="workspace",
            workspace_root=workspace_root,
        )
    return plugin_state_path(
        plugin_id=plugin_id,
        scope="global",
        pawrrtal_home=pawrrtal_home or default_pawrrtal_home(),
    )


def _outcome(
    *,
    plugin: DiscoveredPlugin,
    state: PluginState,
    status: PluginLoadStatus,
    reason: str | None,
    missing_env: tuple[str, ...] = (),
) -> PluginLoadOutcome:
    """Build one load outcome for a valid manifest."""
    if plugin.manifest is None:
        raise ValueError("valid manifest required for plugin outcome")
    return PluginLoadOutcome(
        plugin_id=plugin.manifest.id,
        source_type=plugin.source_type,
        manifest_path=plugin.manifest_path,
        status=status,
        reason=reason,
        fingerprint=plugin.fingerprint,
        state=state,
        manifest=plugin.manifest,
        missing_env=missing_env,
    )


def _apply_dependency_status(
    outcomes: tuple[PluginLoadOutcome, ...],
) -> tuple[PluginLoadOutcome, ...]:
    """Mark active plugins blocked when dependencies are not active."""
    by_id = {outcome.plugin_id: outcome for outcome in outcomes}
    blocked: list[PluginLoadOutcome] = []
    for outcome in outcomes:
        if not outcome.active or outcome.manifest is None:
            blocked.append(outcome)
            continue
        missing = [
            dependency.id
            for dependency in outcome.manifest.depends_on
            if not by_id.get(dependency.id) or not by_id[dependency.id].active
        ]
        if missing:
            blocked.append(
                replace(
                    outcome,
                    status="blocked_by_dependency",
                    reason=f"Dependencies are not active: {', '.join(missing)}.",
                )
            )
            continue
        blocked.append(outcome)
    return tuple(blocked)


def _catalog_capabilities(outcomes: tuple[PluginLoadOutcome, ...]) -> tuple[CapabilityRecord, ...]:
    """Return capability rows for active and unavailable plugins."""
    records: list[CapabilityRecord] = []
    for outcome in outcomes:
        if outcome.manifest is None:
            continue
        for capability in outcome.manifest.capabilities:
            state = _capability_state(outcome, capability.id)
            records.append(
                CapabilityRecord.from_capability(
                    plugin_id=outcome.plugin_id,
                    capability=capability,
                    state=state,
                )
            )
    return tuple(records)


def _capability_state(outcome: PluginLoadOutcome, capability_id: str) -> CapabilityState:
    """Return the effective catalog state for one capability."""
    if not outcome.active:
        return _status_to_capability_state(outcome.status)
    return "enabled" if outcome.state.is_capability_enabled(capability_id) else "disabled"


def _status_to_capability_state(status: PluginLoadStatus) -> CapabilityState:
    """Project plugin load status onto capability state."""
    if status == "active":
        return "enabled"
    if status == "blocked_by_dependency":
        return "blocked_by_dependency"
    if status in {"disabled", "needs_validation", "misconfigured", "failed"}:
        return status
    return "failed"


def _snapshot_fingerprint(
    workspace_key: str,
    outcomes: tuple[PluginLoadOutcome, ...],
    capabilities: tuple[CapabilityRecord, ...],
) -> str:
    """Hash plugin/capability state for hot-reload comparisons."""
    payload = {
        "workspace_key": workspace_key,
        "outcomes": [
            {
                "plugin_id": outcome.plugin_id,
                "status": outcome.status,
                "fingerprint": outcome.fingerprint,
                "enabled": outcome.state.enabled,
                "missing_env": outcome.missing_env,
            }
            for outcome in outcomes
        ],
        "capabilities": [capability.to_wire() for capability in capabilities],
    }
    return _hash_payload(payload)


def _workspace_key(workspace_root: Path | None) -> str:
    """Return a stable host-map key for a workspace snapshot."""
    if workspace_root is None:
        return "global"
    return str(workspace_root.resolve())


def _hash_payload(payload: object) -> str:
    """Return a stable SHA-256 hash for a JSON payload."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
