"""GoogleChatChannel — progressive message-patch delivery via Chat REST.

Mirrors :class:`app.channels.telegram.channel.TelegramChannel`: a single
stateless ``Channel`` instance whose ``deliver`` consumes LLM stream
events and pushes them to the surface as a side-effect (yielding no
bytes). The ingress pre-creates a "working" placeholder message and
passes its resource name in ``ChannelMessage.metadata``; ``deliver``
hands the stream to a :class:`StreamingDelivery`, which patches that one
message in place as the answer (and, per verbosity, the tool calls and
thinking) stream in.

The debounce + render logic lives in :mod:`.delivery`; this module only
wires the ``Channel`` protocol to it.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.channels.base import ChannelMessage
from app.providers.base import StreamEvent

from .delivery import DEFAULT_VERBOSE_LEVEL, StreamingDelivery

logger = logging.getLogger(__name__)

SURFACE_GOOGLE_CHAT = "google_chat"

# Text the ingress writes into the placeholder so the user gets instant
# acknowledgement before the model produces its first token.
INITIAL_PLACEHOLDER_TEXT = "🐾 Working…"


class GoogleChatChannel:
    """``Channel`` implementation for Google Chat via Chat REST message edits.

    Instantiated once and shared across requests — it holds no per-request
    state. All per-request context (the placeholder message name and the
    verbosity level) travels through ``ChannelMessage.metadata``.
    """

    surface: str = SURFACE_GOOGLE_CHAT

    async def deliver(
        self,
        stream: AsyncIterator[StreamEvent],
        message: ChannelMessage,
    ) -> AsyncIterator[bytes]:
        """Consume LLM events and patch the Chat placeholder as they stream.

        Expected ``message["metadata"]`` keys:

        - ``message_name`` (``str``): the ``spaces/*/messages/*`` resource
          name of the placeholder created by the ingress.
        - ``verbose_level`` (``int``, optional): 0 quiet, 1 tools, 2 thinking.

        Yields nothing — all delivery is via side-effects.

        Args:
            stream: Async iterator of ``StreamEvent`` dicts from the LLM.
            message: Originating ``ChannelMessage`` — metadata carries the
                     Chat-specific routing context.
        """
        meta: dict[str, Any] = message["metadata"]
        message_name: str | None = meta.get("message_name")
        verbose_level = int(meta.get("verbose_level", DEFAULT_VERBOSE_LEVEL))

        if message_name is None:
            # No placeholder to patch — the ingress failed to create one
            # (logged there). Nothing to deliver into.
            logger.warning(
                "GOOGLE_CHAT_DELIVER_NO_PLACEHOLDER conversation_id=%s", message["conversation_id"]
            )
            return
            # See the unreachable yield note below.
            yield  # pragma: no cover

        delivery = StreamingDelivery(message_name=message_name, verbose_level=verbose_level)
        async for event in stream:
            await delivery.on_event(event)
        await delivery.finalize()

        # No bytes to yield — delivery is a side-effect only. The bare
        # ``yield`` below is unreachable but required so this function is
        # an async generator (the ``Channel.deliver`` protocol shape).
        return
        yield  # pragma: no cover
