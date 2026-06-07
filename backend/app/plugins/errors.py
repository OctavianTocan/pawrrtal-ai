"""Shared errors for the dynamic plugin host."""

from __future__ import annotations


class PluginError(ValueError):
    """Base class for plugin platform validation and loading failures."""


class PluginManifestError(PluginError):
    """Raised when a plugin manifest violates the platform contract."""


class PluginDiscoveryError(PluginError):
    """Raised when discovery finds conflicting or invalid plugin sources."""


class PluginStateError(PluginError):
    """Raised when persisted plugin state is malformed or cannot be written."""


class PluginRuntimeError(PluginError):
    """Raised when a plugin contribution cannot be prepared for runtime use."""
