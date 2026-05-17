"""Channel registry — maps surface names to Channel implementations.

The registry is a lightweight lookup table.  It is intentionally not a
global singleton that auto-discovers implementations; channels are registered
explicitly so the set of active channels is always visible in one place.

Usage
-----
::

    from app.channels.registry import resolve_channel

    channel = resolve_channel("web")      # SSEChannel(surface="web")
    channel = resolve_channel("electron") # SSEChannel(surface="electron")
    channel = resolve_channel("telegram") # TelegramChannel (future)

Extending
---------
When a new channel adapter is added, import it here and register it via
``_REGISTRY``.  No other file needs to change.
"""

from __future__ import annotations

from .base import Channel
from .sse import SURFACE_ELECTRON, SURFACE_WEB, SSEChannel

# ---------------------------------------------------------------------------
# Registry — explicit mapping of surface name → Channel instance.
#
# Channels are stateless singletons: they hold no per-request state, so one
# instance per surface is safe and cheap.
#
# NOTE: Telegram registration was removed in the practice-telegram branch.
# Re-register here when the TelegramChannel adapter is rebuilt — see the
# corresponding bean for the full requirements.
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Channel] = {
    SURFACE_WEB: SSEChannel(surface=SURFACE_WEB),
    # TODO: Is this necessary? What's the point of defining a separate surface if we're basically reusing web for this.
    SURFACE_ELECTRON: SSEChannel(surface=SURFACE_ELECTRON),
    # TODO(pawrrtal-bn6c): add the Telegram entry once Phase 5 ships
    #   the adapter. Stateless singleton — one instance, shared across
    #   every Telegram turn.
}


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
    return _REGISTRY.get(surface, _REGISTRY[SURFACE_WEB])


def registered_surfaces() -> list[str]:
    """Return the list of registered surface names (for introspection/tests)."""
    return list(_REGISTRY.keys())
