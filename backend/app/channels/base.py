"""Channel abstraction — base protocol and shared message types.

Every surface that can send a message to Pawrrtal and receive a response is a
Channel.  Channels are equal peers; there is no "default" channel.

Architecture
------------
- ``ChannelMessage`` — normalized inbound shape produced by any channel.
- ``ChannelResponse`` — normalized outbound shape consumed by any channel.
- ``Channel`` — protocol that every adapter must implement.

The split between *inbound normalization* and *outbound delivery* maps to
the two directions of data flow:

    raw surface event
        → Channel.receive()          ← normalize to ChannelMessage
        → resolve_llm() / run_model_tool_loop ← core is channel-agnostic
        → Channel.deliver()          ← surface-specific delivery
        → raw surface output

Current implementations
-----------------------
- ``SSEChannel`` (app.channels.sse) — HTTP Server-Sent Events; used by the
  web frontend and the Electron desktop shell.

Planned
-------
- ``TelegramChannel`` — aiogram polling/webhook + progressive message edits.
- ``MobileChannel`` — SSE + APNs/FCM push for background delivery.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol, TypedDict

from app.providers.base import StreamEvent

# ---------------------------------------------------------------------------
# Normalized message types
# ---------------------------------------------------------------------------


class ChannelMessage(TypedDict):
    """Normalized inbound message produced by ``Channel.receive()``.

    Every channel reduces its raw event (HTTP body, Telegram Update, IPC
    payload, …) to this common shape before the message enters the core
    turn pipeline.
    """

    user_id: uuid.UUID
    """Pawrrtal user UUID — resolved from auth token or channel binding."""

    conversation_id: uuid.UUID
    """Pawrrtal conversation UUID — created or looked up by the channel."""

    text: str
    """The user's message text."""

    surface: str
    """Identifies the originating surface, e.g. ``"web"``, ``"electron"``,
    ``"telegram"``.  Used for logging, analytics, and any surface-specific
    behaviour the core layer needs to branch on."""

    model_id: str | None
    """Optional LLM model override requested by the client."""

    metadata: dict[str, Any]
    """Catch-all for surface-specific extras (e.g. Telegram chat_id, message_id)
    that the delivery layer needs but the core layer should never inspect."""


class ChannelResponse(TypedDict, total=False):
    """Normalized outbound event consumed by ``Channel.deliver()``.

    This is a thin wrapper around ``StreamEvent`` that adds routing context
    so the delivery layer knows *where* to send the response.
    """

    event: StreamEvent
    """The LLM-layer stream event to deliver."""

    done: bool
    """True on the final event of a turn (signals ``[DONE]`` or equivalent)."""


# ---------------------------------------------------------------------------
# Channel protocol
# ---------------------------------------------------------------------------


class Channel(Protocol):
    """Streaming chat channel adapter.

    Implementations translate between a surface's native protocol and the
    Pawrrtal core pipeline.  Each implementation is responsible for:

    1. **Normalization** (``receive``): converting the raw inbound event
       into a ``ChannelMessage``.
    2. **Delivery** (``deliver``): consuming ``StreamEvent`` s from the LLM
       pipeline and pushing them back to the surface in whatever format it
       expects (SSE frames, Telegram message edits, push payloads, …).

    Implementations are *not* responsible for authentication, LLM routing,
    or history management — those belong to the core layer.
    """

    surface: str
    """Canonical surface name, e.g. ``"web"``, ``"electron"``, ``"telegram"``."""

    def deliver(
        self,
        stream: AsyncIterator[StreamEvent],
        message: ChannelMessage,
    ) -> AsyncIterator[bytes]:
        """Consume LLM stream events and yield surface-appropriate bytes.

        For SSE channels this is newline-framed JSON.  For Telegram this
        would drive ``edit_message_text`` calls and yield nothing (delivery
        is a side-effect).  The protocol uses ``bytes`` as the common
        denominator; channels that deliver via side-effect yield nothing.

        Args:
            stream: Async iterator of ``StreamEvent`` dicts from the LLM.
            message: The originating ``ChannelMessage`` — delivery may need
                     metadata from it (e.g. Telegram ``chat_id``).

        Yields:
            Surface-encoded bytes to hand to the transport layer.
        """
        ...
