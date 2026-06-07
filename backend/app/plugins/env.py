"""Workspace-aware env resolution for plugin-declared keys."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.infrastructure.keys import load_workspace_env
from app.plugins.contributions import EnvVarSpec
from app.plugins.discovery import default_plugin_roots, discover_plugins
from app.plugins.manifest import PluginManifest


@dataclass(frozen=True, slots=True)
class EnvResolution:
    """Resolved value metadata for one plugin env key."""

    name: str
    inject_as: str
    configured: bool
    source: str | None
    value: str | None


@dataclass(frozen=True, slots=True)
class PluginEnvStatus:
    """Workspace-specific env status for one plugin."""

    configured: bool
    missing_required: tuple[str, ...]


def resolve_plugin_env(
    *,
    workspace_root: Path | None,
    spec: EnvVarSpec,
) -> EnvResolution:
    """Resolve one plugin env declaration without exposing it to callers."""
    workspace_value = _workspace_value(workspace_root, spec)
    if workspace_value:
        return EnvResolution(
            name=spec.name,
            inject_as=spec.inject_as or spec.name,
            configured=True,
            source="workspace",
            value=workspace_value,
        )

    gateway_value = _gateway_value(spec)
    if gateway_value:
        return EnvResolution(
            name=spec.name,
            inject_as=spec.inject_as or spec.name,
            configured=True,
            source="gateway",
            value=gateway_value,
        )

    return EnvResolution(
        name=spec.name,
        inject_as=spec.inject_as or spec.name,
        configured=False,
        source=None,
        value=None,
    )


def plugin_env_status(
    *,
    workspace_root: Path | None,
    manifest: PluginManifest,
) -> PluginEnvStatus:
    """Return whether all required env keys are configured for a workspace."""
    missing: list[str] = []
    for spec in manifest.all_env_specs():
        resolution = resolve_plugin_env(workspace_root=workspace_root, spec=spec)
        if spec.required and not resolution.configured:
            missing.append(spec.name)
    return PluginEnvStatus(configured=not missing, missing_required=tuple(missing))


def plugin_env_specs_for_workspace(
    *,
    workspace_root: Path,
    pawrrtal_home: Path | None = None,
) -> tuple[EnvVarSpec, ...]:
    """Return plugin-declared env specs users may configure in one workspace."""
    specs: list[EnvVarSpec] = []
    seen: set[str] = set()
    discovered = discover_plugins(
        default_plugin_roots(workspace_root=workspace_root, pawrrtal_home=pawrrtal_home)
    )
    for plugin in discovered:
        if plugin.manifest is None:
            continue
        for spec in plugin.manifest.all_env_specs():
            if spec.name in seen or not _is_workspace_overridable(spec):
                continue
            specs.append(spec)
            seen.add(spec.name)
    return tuple(specs)


def plugin_overridable_env_keys(
    *,
    workspace_root: Path,
    pawrrtal_home: Path | None = None,
) -> frozenset[str]:
    """Return env key names users may configure because plugins declare them."""
    return frozenset(
        spec.name
        for spec in plugin_env_specs_for_workspace(
            workspace_root=workspace_root,
            pawrrtal_home=pawrrtal_home,
        )
    )


def _workspace_value(workspace_root: Path | None, spec: EnvVarSpec) -> str | None:
    """Return the active workspace override when the scope permits it."""
    if workspace_root is None or spec.scope == "gateway":
        return None
    value = load_workspace_env(workspace_root).get(spec.name)
    return value or None


def _gateway_value(spec: EnvVarSpec) -> str | None:
    """Return a gateway/process value when the spec permits it."""
    if spec.scope == "gateway" or spec.gateway_fallback:
        return os.environ.get(spec.name) or None
    return None


def _is_workspace_overridable(spec: EnvVarSpec) -> bool:
    """Return whether the workspace env API should expose this plugin key."""
    return spec.overridable and spec.scope in {"workspace", "user_workspace"}
