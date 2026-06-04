"""GoogleChatChannel — message-patch delivery via the Chat REST API.

Mirrors :class:`app.channels.telegram.channel.TelegramChannel`: a single
stateless ``Channel`` instance whose ``deliver`` consumes LLM stream
events and pushes them to the surface as a side-effect (yielding no
bytes). The ingress pre-creates a "working" placeholder message and
passes its resource name in ``ChannelMessage.metadata``; ``deliver``
accumulates the answer text and patches that one message once at the
end.

Why a single final patch (not progressive edits): Google Chat exposes
no streaming or typing API — the only progressive option is repeated
``messages.patch`` calls, and Google publishes no rate limit for them.
For v1 we make exactly one edit per turn (placeholder → final answer),
which is both the simplest and the rate-limit-safe choice. Debounced
progressive edits are a documented follow-up.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.channels.base import ChannelMessage
from app.providers.base import StreamEvent

from .client import update_message
from .messages import format_for_chat

logger = logging.getLogger(__name__)

SURFACE_GOOGLE_CHAT = "google_chat"

# Text the ingress writes into the placeholder so the user gets instant
# acknowledgement before the model produces its first token.
INITIAL_PLACEHOLDER_TEXT = "🐾 Working…"

# Prefix for surfaced error outcomes (kept short to match the Telegram
# channel's restraint).
_ERROR_PREFIX = "❌ "

# Shown when a turn produces neither text nor a structured error, so the
# placeholder never sits on "Working…" forever.
_EMPTY_RESPONSE_FALLBACK = "⚠️ The agent finished without producing a reply. Please try again."


class GoogleChatChannel:
    """``Channel`` implementation for Google Chat via Chat REST message edits.

    Instantiated once and shared across requests — it holds no per-request
    state. All per-request context (the placeholder message name) travels
    through ``ChannelMessage.metadata``.
    """

    surface: str = SURFACE_GOOGLE_CHAT

    async def deliver(
        self,
        stream: AsyncIterator[StreamEvent],
        message: ChannelMessage,
    ) -> AsyncIterator[bytes]:
        """Consume LLM events and patch the Chat placeholder with the result.

        Expected ``message["metadata"]`` keys:

        - ``message_name`` (``str``): the ``spaces/*/messages/*`` resource
          name of the placeholder created by the ingress.

        Yields nothing — all delivery is via side-effects.

        Args:
            stream: Async iterator of ``StreamEvent`` dicts from the LLM.
            message: Originating ``ChannelMessage`` — metadata carries the
                     Chat-specific routing context.
        """
        meta: dict[str, Any] = message["metadata"]
        message_name: str | None = meta.get("message_name")

        answer = ""
        error_text: str | None = None
        async for event in stream:
            etype = event.get("type")
            if etype == "delta":
                answer += event.get("content") or ""
            elif etype == "error":
                error_text = str(event.get("content") or "Something went wrong.")

        if message_name is None:
            # No placeholder to patch — the ingress failed to create one
            # (logged there). Nothing to deliver into.
            logger.warning(
                "GOOGLE_CHAT_DELIVER_NO_PLACEHOLDER conversation_id=%s", message["conversation_id"]
            )
            return
            # See the unreachable yield note below.
            yield  # pragma: no cover

        final_text = _final_text(answer=answer, error_text=error_text)
        await update_message(message_name=message_name, text=format_for_chat(final_text))

        # No bytes to yield — delivery is a side-effect only. The bare
        # ``yield`` below is unreachable but required so this function is
        # an async generator (the ``Channel.deliver`` protocol shape).
        return
        yield  # pragma: no cover


def _final_text(*, answer: str, error_text: str | None) -> str:
    """Resolve the single text to patch into the placeholder.

    An error wins (the user must know the turn failed), then any
    accumulated answer, then the empty-turn fallback.
    """
    if error_text is not None:
        return f"{_ERROR_PREFIX}{error_text}"
    if answer.strip():
        return answer
    return _EMPTY_RESPONSE_FALLBACK
