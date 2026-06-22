"""Channel abstraction layer for Pawrrtal.

Every surface that can send a message and receive a response is a Channel.
This package provides:

- ``Channel`` — protocol that all adapters implement.
- ``ChannelMessage`` / ``ChannelResponse`` — normalized inbound/outbound types.
- ``SSEChannel`` — HTTP SSE adapter (web + Electron).
- ``resolve_channel(surface)`` — look up a Channel by surface name.
- ``registered_surfaces()`` — introspect active channel registrations.
"""

# <skill-gen>
# ---
# name: extension-boundaries
# description: Use when touching Pawrrtal channels, providers, tools, plugins, subagents, context providers, turn orchestration, or code that decides where an integration should live. Enforces the split between generic kernel code, manifest plugins, trusted runtime adapters, provider adapters, channel adapters, and agent runtime primitives.
# ---
#
# # Pawrrtal Extension Boundaries
#
# Use this before changing backend extension code. The goal is a thin generic
# kernel with optional pieces installed as plugins.
#
# ## Channel Adapters
#
# A channel adapter talks to one user surface, such as Telegram or Google Chat.
# Channel-specific code belongs under `backend/app/channels/<channel>/` or
# behind a channel plugin capability.
#
# Channel adapters should:
#
# - Normalize inbound/outbound messages through the channel base types.
# - Choose a model and call the generic turn runner.
# - Keep provider internals, SDK payloads, and tool factories out of channel code.
# - Move reusable formatting to channel runtime helpers or a channel adapter.
#
# If a new surface can send a message and receive a response, treat it as a
# channel unless it is purely a local CLI/operator concern.
# </skill-gen>

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
