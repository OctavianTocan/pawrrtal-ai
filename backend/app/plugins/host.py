"""Process-local plugin host with workspace-keyed immutable snapshots."""

from __future__ import annotations

from pathlib import Path
from threading import RLock

from app.plugins.discovery import default_plugin_roots, discover_plugins
from app.plugins.registry import ContributionRegistrySnapshot, build_registry_snapshot


class PluginHost:
    """Holds current plugin registry snapshots keyed by workspace."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshots: dict[str, ContributionRegistrySnapshot] = {}

    def snapshot(self, *, workspace_root: Path | None = None) -> ContributionRegistrySnapshot:
        """Return the current immutable snapshot for a workspace."""
        key = _workspace_key(workspace_root)
        with self._lock:
            return self._snapshots.get(key) or ContributionRegistrySnapshot.empty(workspace_key=key)

    def reload(
        self,
        *,
        workspace_root: Path | None = None,
        pawrrtal_home: Path | None = None,
    ) -> tuple[ContributionRegistrySnapshot, ContributionRegistrySnapshot]:
        """Build and publish a new workspace snapshot without mutating the old one."""
        key = _workspace_key(workspace_root)
        roots = default_plugin_roots(workspace_root=workspace_root, pawrrtal_home=pawrrtal_home)
        discovered = discover_plugins(roots)
        next_snapshot = build_registry_snapshot(
            discovered,
            workspace_root=workspace_root,
            pawrrtal_home=pawrrtal_home,
        )
        with self._lock:
            previous = self._snapshots.get(key) or ContributionRegistrySnapshot.empty(
                workspace_key=key
            )
            self._snapshots[key] = next_snapshot
        return previous, next_snapshot


_HOST = PluginHost()


def get_plugin_host() -> PluginHost:
    """Return the process-wide plugin host."""
    return _HOST


def _workspace_key(workspace_root: Path | None) -> str:
    """Return the cache key for one workspace snapshot."""
    if workspace_root is None:
        return "global"
    return str(workspace_root.resolve())
