"""Manifest discovery across bundled, global, and workspace plugin roots."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.plugins.errors import PluginDiscoveryError, PluginManifestError
from app.plugins.fingerprints import fingerprint_plugin
from app.plugins.manifest import PluginManifest, PluginSourceType, validate_plugin_manifest


@dataclass(frozen=True, slots=True)
class PluginRoot:
    """One root directory searched for plugin manifests."""

    source_type: PluginSourceType
    path: Path


@dataclass(frozen=True, slots=True)
class DiscoveredPlugin:
    """One plugin manifest candidate found on disk."""

    plugin_id: str
    source_type: PluginSourceType
    plugin_dir: Path
    manifest_path: Path
    manifest: PluginManifest | None
    fingerprint: str | None
    error: str | None = None

    @property
    def valid(self) -> bool:
        """Return whether discovery parsed and fingerprinted the manifest."""
        return self.manifest is not None and self.fingerprint is not None and self.error is None


def default_pawrrtal_home() -> Path:
    """Return the global Pawrrtal data root."""
    return Path(os.environ.get("PAWRRTAL_HOME", Path.home() / ".pawrrtal")).expanduser()


def bundled_plugins_root() -> Path:
    """Return the repository bundled-plugin root."""
    return Path(__file__).resolve().parents[2] / "plugins"


def default_plugin_roots(
    *,
    workspace_root: Path | None = None,
    pawrrtal_home: Path | None = None,
) -> tuple[PluginRoot, ...]:
    """Return plugin roots in increasing precedence order."""
    home = pawrrtal_home or default_pawrrtal_home()
    roots: list[PluginRoot] = [
        PluginRoot(source_type="bundled", path=bundled_plugins_root()),
        PluginRoot(source_type="global", path=home / "plugins"),
    ]
    if workspace_root is not None:
        roots.append(
            PluginRoot(source_type="workspace", path=workspace_root / ".agent" / "plugins")
        )
    return tuple(roots)


def discover_plugins(roots: tuple[PluginRoot, ...]) -> tuple[DiscoveredPlugin, ...]:
    """Discover manifests and apply explicit override precedence rules."""
    chosen: dict[str, DiscoveredPlugin] = {}
    for root in roots:
        for manifest_path in _manifest_paths(root.path):
            discovered = _load_discovered_plugin(root, manifest_path)
            existing = chosen.get(discovered.plugin_id)
            if existing is None:
                chosen[discovered.plugin_id] = discovered
                continue
            if _explicitly_overrides(discovered, existing):
                chosen[discovered.plugin_id] = discovered
                continue
            raise PluginDiscoveryError(
                "Duplicate plugin id "
                f"{discovered.plugin_id!r} at {manifest_path}; set overrides explicitly."
            )
    return tuple(chosen.values())


def _manifest_paths(root: Path) -> tuple[Path, ...]:
    """Return direct child ``plugin.json`` paths under a root."""
    if not root.exists():
        return ()
    paths = [path for path in root.iterdir() if (path / "plugin.json").is_file()]
    return tuple(sorted(path / "plugin.json" for path in paths))


def _load_discovered_plugin(root: PluginRoot, manifest_path: Path) -> DiscoveredPlugin:
    """Load one manifest from a known root without raising on bad plugins."""
    plugin_id = manifest_path.parent.name
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = validate_plugin_manifest(raw, source_type=root.source_type)
        return DiscoveredPlugin(
            plugin_id=manifest.id,
            source_type=root.source_type,
            plugin_dir=manifest_path.parent,
            manifest_path=manifest_path,
            manifest=manifest,
            fingerprint=fingerprint_plugin(manifest_path.parent, manifest),
        )
    except (OSError, json.JSONDecodeError, PluginManifestError) as exc:
        return DiscoveredPlugin(
            plugin_id=plugin_id,
            source_type=root.source_type,
            plugin_dir=manifest_path.parent,
            manifest_path=manifest_path,
            manifest=None,
            fingerprint=None,
            error=str(exc),
        )


def _explicitly_overrides(
    discovered: DiscoveredPlugin,
    existing: DiscoveredPlugin,
) -> bool:
    """Return whether ``discovered`` explicitly overrides ``existing``."""
    if discovered.manifest is None:
        return False
    return discovered.manifest.overrides == existing.plugin_id
