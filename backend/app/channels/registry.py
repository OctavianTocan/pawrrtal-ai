"""Channel registry — maps surface names to active Channel implementations.

Channels are declared as plugin capabilities and composed through the plugin
host. The kernel keeps only a web SSE fallback so unknown or disabled surfaces
still have a safe response path.

Usage
-----
::

    from app.channels.registry import resolve_channel

    channel = resolve_channel("web")      # SSEChannel(surface="web")
    channel = resolve_channel("electron") # SSEChannel(surface="electron")
    channel = resolve_channel("telegram") # TelegramChannel when enabled

Extending
---------
Add a trusted ``channel`` capability to a bundled or global plugin manifest.
"""

from __future__ import annotations

from app.plugins.adapters.channels import build_channel_registry

from .base import Channel
from .sse import SURFACE_WEB, SSEChannel


def _fallback_registry() -> dict[str, Channel]:
    """Return kernel-owned fallback channels."""
    return {SURFACE_WEB: SSEChannel(surface=SURFACE_WEB)}


def _registry() -> dict[str, Channel]:
    """Return active plugin channels plus the mandatory web fallback."""
    registry = _fallback_registry()
    registry.update(build_channel_registry())
    return registry


def resolve_channel(surface: str) -> Channel:
    """Return the ``Channel`` registered for *surface*.

    Falls back to the web SSE channel for unrecognized surface names so that
    new clients that haven't registered their surface yet don't crash.

    Args:
        surface: Canonical surface name, e.g. ``"web"``, ``"electron"``,
                 ``"telegram"``.

    Returns:
        The registered ``Channel`` instance.
    """
    registry = _registry()
    return registry.get(surface, registry[SURFACE_WEB])


def registered_surfaces() -> list[str]:
    """Return the list of registered surface names (for introspection/tests)."""
    return list(_registry().keys())
