r"""SSEChannel — HTTP Server-Sent Events delivery for web and Electron.

Both the web frontend and the Electron desktop shell connect over HTTP and
consume the same SSE stream format, so a single ``SSEChannel`` implementation
covers both surfaces.  The ``surface`` field on ``ChannelMessage`` records
which one originated the request (``"web"`` vs ``"electron"``), but the
delivery path is identical.

SSE frame format
----------------
Each event is serialized as::

    data: <json>\n\n

A turn is terminated by::

    data: [DONE]\n\n

This matches the existing format the frontend's ``EventSource`` parser
expects, so the channel is a drop-in replacement for the previous inline
``event_stream()`` generator in ``chat.py``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from app.providers.base import StreamEvent

from .base import Channel, ChannelMessage

# Sentinel surface names recognized by the registry.
SURFACE_WEB = "web"
SURFACE_ELECTRON = "electron"

# HTTP header the frontend sets to identify itself.
# If absent, the channel defaults to SURFACE_WEB.
NEXUS_SURFACE_HEADER = "X-Pawrrtal-Surface"


def _frame(event: StreamEvent) -> bytes:
    """Serialize a ``StreamEvent`` as a single SSE data frame."""
    return f"data: {json.dumps(event)}\n\n".encode()


_DONE_FRAME = b"data: [DONE]\n\n"


class SSEChannel(Channel):
    """``Channel`` implementation for HTTP SSE (web + Electron).

    Instantiated once and shared across requests — it holds no per-request
    state. Explicitly inheriting from ``Channel`` makes mypy/pyright
    enforce protocol conformance at class-definition time rather than at
    each call site.
    """

    def __init__(self, surface: str = SURFACE_WEB) -> None:
        self.surface = surface

    async def deliver(
        self,
        stream: AsyncIterator[StreamEvent],
        message: ChannelMessage,
    ) -> AsyncIterator[bytes]:
        """Yield SSE-framed bytes for every event in *stream*, then ``[DONE]``.

        The caller wraps the returned iterator in a ``StreamingResponse``
        with ``media_type="text/event-stream"``.

        Args:
            stream: Async iterator of ``StreamEvent`` dicts from the LLM.
            message: Originating ``ChannelMessage`` (unused by SSE delivery
                     but required by the ``Channel`` protocol for surfaces
                     that need it, e.g. Telegram).

        Yields:
            UTF-8 encoded SSE frames.
        """
        async for event in stream:
            yield _frame(event)
        yield _DONE_FRAME


def surface_from_header(header_value: str | None) -> str:
    """Resolve the surface name from the ``X-Pawrrtal-Surface`` request header.

    Accepts ``"web"`` and ``"electron"``; defaults to ``"web"`` for any
    unrecognized or absent value so existing clients that don't send the
    header keep working.

    Args:
        header_value: Raw header string, or ``None`` if the header is absent.

    Returns:
        Canonical surface name — either ``SURFACE_WEB`` or ``SURFACE_ELECTRON``.
    """
    if header_value and header_value.lower() == SURFACE_ELECTRON:
        return SURFACE_ELECTRON
    return SURFACE_WEB
