"""Channel abstraction layer for Pawrrtal.

Every surface that can send a message and receive a response is a Channel.
This package provides:

- ``Channel`` — protocol that all adapters implement.
- ``ChannelMessage`` / ``ChannelResponse`` — normalized inbound/outbound types.
- ``SSEChannel`` — HTTP SSE adapter (web + Electron).
- ``resolve_channel(surface)`` — look up a Channel by surface name.
- ``registered_surfaces()`` — introspect active channel registrations.
"""

from .base import Channel, ChannelMessage, ChannelResponse
from .registry import registered_surfaces, resolve_channel
from .sse import SSEChannel, surface_from_header

__all__ = [
    "Channel",
    "ChannelMessage",
    "ChannelResponse",
    "SSEChannel",
    "registered_surfaces",
    "resolve_channel",
    "surface_from_header",
]
