"""Tests for the channel abstraction layer.

Covers:
- ``surface_from_header`` — header parsing + defaults
- ``resolve_channel`` — registry lookup + unknown-surface fallback
- ``registered_surfaces`` — introspection
- ``SSEChannel.deliver`` — SSE frame encoding
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.channels import (
    SSEChannel,
    registered_surfaces,
    resolve_channel,
    surface_from_header,
)
from app.channels.sse import SURFACE_ELECTRON, SURFACE_WEB

# ---------------------------------------------------------------------------
# surface_from_header
# ---------------------------------------------------------------------------


class TestSurfaceFromHeader:
    def test_none_defaults_to_web(self) -> None:
        assert surface_from_header(None) == SURFACE_WEB

    def test_empty_string_defaults_to_web(self) -> None:
        assert surface_from_header("") == SURFACE_WEB

    def test_web_returns_web(self) -> None:
        assert surface_from_header("web") == SURFACE_WEB

    def test_electron_returns_electron(self) -> None:
        assert surface_from_header("electron") == SURFACE_ELECTRON

    def test_electron_case_insensitive(self) -> None:
        assert surface_from_header("Electron") == SURFACE_ELECTRON
        assert surface_from_header("ELECTRON") == SURFACE_ELECTRON

    def test_unknown_value_defaults_to_web(self) -> None:
        assert surface_from_header("mobile") == SURFACE_WEB
        assert surface_from_header("telegram") == SURFACE_WEB


# ---------------------------------------------------------------------------
# resolve_channel
# ---------------------------------------------------------------------------


class TestResolveChannel:
    def test_web_returns_sse_channel(self) -> None:
        ch = resolve_channel("web")
        assert isinstance(ch, SSEChannel)
        assert ch.surface == SURFACE_WEB

    def test_electron_returns_sse_channel(self) -> None:
        ch = resolve_channel("electron")
        assert isinstance(ch, SSEChannel)
        assert ch.surface == SURFACE_ELECTRON

    def test_unknown_surface_falls_back_to_web(self) -> None:
        ch = resolve_channel("unknown-surface")
        assert isinstance(ch, SSEChannel)
        assert ch.surface == SURFACE_WEB

    def test_web_and_electron_are_same_type_but_distinct_instances(self) -> None:
        web = resolve_channel("web")
        electron = resolve_channel("electron")
        assert type(web) is type(electron)
        assert web is not electron


# ---------------------------------------------------------------------------
# registered_surfaces
# ---------------------------------------------------------------------------


class TestRegisteredSurfaces:
    def test_contains_web(self) -> None:
        assert "web" in registered_surfaces()

    def test_contains_electron(self) -> None:
        assert "electron" in registered_surfaces()

    def test_returns_list(self) -> None:
        assert isinstance(registered_surfaces(), list)


# ---------------------------------------------------------------------------
# SSEChannel.deliver
# ---------------------------------------------------------------------------


async def _make_stream(events: list[Any]) -> AsyncIterator[Any]:
    """Helper — yield a list of events as an async iterator."""
    for event in events:
        yield event


class TestSSEChannelDeliver:
    @pytest.mark.anyio
    async def test_yields_json_frames(self) -> None:
        channel = SSEChannel(surface="web")
        events = [
            {"type": "delta", "content": "Hello"},
            {"type": "delta", "content": " world"},
        ]
        import uuid

        from app.channels.base import ChannelMessage

        msg: ChannelMessage = {
            "user_id": uuid.uuid4(),
            "conversation_id": uuid.uuid4(),
            "text": "hi",
            "surface": "web",
            "model_id": None,
            "metadata": {},
        }

        chunks = [chunk async for chunk in channel.deliver(_make_stream(events), msg)]

        # Two data frames + the [DONE] sentinel
        assert len(chunks) == 3

        # Each event frame must be valid SSE and deserialize to the original dict
        for chunk, event in zip(chunks[:2], events, strict=True):
            assert chunk.startswith(b"data: ")
            assert chunk.endswith(b"\n\n")
            payload = json.loads(chunk[len("data: ") :].strip())
            assert payload == event

    @pytest.mark.anyio
    async def test_done_frame_is_last(self) -> None:
        channel = SSEChannel(surface="electron")
        import uuid

        from app.channels.base import ChannelMessage

        msg: ChannelMessage = {
            "user_id": uuid.uuid4(),
            "conversation_id": uuid.uuid4(),
            "text": "hi",
            "surface": "electron",
            "model_id": None,
            "metadata": {},
        }

        chunks = [
            chunk
            async for chunk in channel.deliver(
                _make_stream([{"type": "delta", "content": "x"}]), msg
            )
        ]

        assert chunks[-1] == b"data: [DONE]\n\n"

    @pytest.mark.anyio
    async def test_empty_stream_only_yields_done(self) -> None:
        channel = SSEChannel(surface="web")
        import uuid

        from app.channels.base import ChannelMessage

        msg: ChannelMessage = {
            "user_id": uuid.uuid4(),
            "conversation_id": uuid.uuid4(),
            "text": "hi",
            "surface": "web",
            "model_id": None,
            "metadata": {},
        }

        chunks = [chunk async for chunk in channel.deliver(_make_stream([]), msg)]

        assert chunks == [b"data: [DONE]\n\n"]

    @pytest.mark.anyio
    async def test_yields_bytes(self) -> None:
        channel = SSEChannel(surface="web")
        import uuid

        from app.channels.base import ChannelMessage

        msg: ChannelMessage = {
            "user_id": uuid.uuid4(),
            "conversation_id": uuid.uuid4(),
            "text": "hi",
            "surface": "web",
            "model_id": None,
            "metadata": {},
        }

        async for chunk in channel.deliver(_make_stream([{"type": "delta", "content": "y"}]), msg):
            assert isinstance(chunk, bytes)
