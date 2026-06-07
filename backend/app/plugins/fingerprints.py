"""Deterministic fingerprints for manifest-declared plugin files."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.plugins.contributions import (
    AgentProfileCapability,
    CliToolCapability,
    SkillCapability,
    ValidationCommand,
)
from app.plugins.errors import PluginManifestError
from app.plugins.manifest import PluginManifest

MAX_FINGERPRINT_FILE_BYTES = 1_000_000


def fingerprint_plugin(plugin_dir: Path, manifest: PluginManifest) -> str:
    """Hash ``plugin.json`` plus local files declared by ``manifest``."""
    digest = hashlib.sha256()
    for path in declared_plugin_files(plugin_dir, manifest):
        relative = path.relative_to(plugin_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_read_declared_file(path))
        digest.update(b"\0")
    return digest.hexdigest()


def declared_plugin_files(plugin_dir: Path, manifest: PluginManifest) -> tuple[Path, ...]:
    """Return the local files that participate in validation fingerprints."""
    declared = {plugin_dir / "plugin.json"}
    for capability in manifest.capabilities:
        if isinstance(capability, CliToolCapability):
            declared.update(_local_entrypoint_files(plugin_dir, capability.entrypoint))
        if isinstance(capability, SkillCapability):
            declared.add(_contained_path(plugin_dir, capability.path))
        if isinstance(capability, AgentProfileCapability):
            declared.add(_contained_path(plugin_dir, capability.instructions))
    for command in manifest.validation.commands:
        declared.update(_validation_command_files(plugin_dir, command))
    return tuple(sorted(declared))


def _validation_command_files(
    plugin_dir: Path,
    command: ValidationCommand,
) -> tuple[Path, ...]:
    """Return local files referenced by one validation command."""
    return _local_entrypoint_files(plugin_dir, command.entrypoint)


def _local_entrypoint_files(plugin_dir: Path, entrypoint: tuple[str, ...]) -> tuple[Path, ...]:
    """Return entrypoint files only when argv points inside the plugin dir."""
    first = entrypoint[0]
    if first.startswith("./") or "/" in first:
        return (_contained_path(plugin_dir, first),)
    return ()


def _contained_path(plugin_dir: Path, relative: str) -> Path:
    """Resolve a declared path and ensure it stays under ``plugin_dir``."""
    raw_path = plugin_dir / relative
    if raw_path.is_symlink():
        raise PluginManifestError(f"Declared plugin file must not be a symlink: {relative}")
    path = raw_path.resolve()
    root = plugin_dir.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PluginManifestError(f"Declared plugin file escapes plugin root: {relative}") from exc
    if not path.is_file():
        raise PluginManifestError(f"Declared plugin file does not exist: {relative}")
    return path


def _read_declared_file(path: Path) -> bytes:
    """Read one declared file after enforcing size and symlink rules."""
    if path.is_symlink():
        raise PluginManifestError(f"Declared plugin file must not be a symlink: {path}")
    size = path.stat().st_size
    if size > MAX_FINGERPRINT_FILE_BYTES:
        raise PluginManifestError(f"Declared plugin file is too large for fingerprinting: {path}")
    return path.read_bytes()
