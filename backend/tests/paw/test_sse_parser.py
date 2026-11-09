"""SSE parser must mirror the frontend's frame-boundary semantics.

Covers ``parse_frame`` (single-frame decode) and ``stream_chat_events``
(byte-level reassembly via ``httpx.MockTransport``). The chunk-splitting
tests are the load-bearing ones: they are what prove the CLI reproduces
the same SSE behavior as the React consumer in
``frontend/features/chat/hooks/use-chat.ts``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from app.cli.paw.sse import KNOWN_EVENT_TYPES, parse_frame, stream_chat_events


def test_parse_frame_single_delta() -> None:
    """A well-formed ``data: {...}`` frame decodes to its JSON payload."""
    frame = b'data: {"type": "delta", "content": "hello"}'
    assert parse_frame(frame) == {"type": "delta", "content": "hello"}


def test_parse_frame_done_sentinel() -> None:
    """The literal ``[DONE]`` sentinel is synthesized into a ``done`` event."""
    assert parse_frame(b"data: [DONE]") == {"type": "done"}


def test_parse_frame_empty() -> None:
    """Empty frames (e.g. leading delimiter) decode to ``None``."""
    assert parse_frame(b"") is None
    assert parse_frame(b"   \n  ") is None


def test_parse_frame_malformed_json_returns_none() -> None:
    """Partial / malformed JSON is treated as an incomplete frame, not an error."""
    assert parse_frame(b'data: {"type": "delta", "content"') is None


def test_parse_frame_multiline_data_payload() -> None:
    """Per the SSE spec, multiple ``data:`` lines join with ``\\n`` before decode."""
    frame = b'data: {"type": "delta",\ndata: "content": "multi"}'
    assert parse_frame(frame) == {"type": "delta", "content": "multi"}


def test_parse_frame_comment_line_ignored() -> None:
    """Lines starting with ``:`` are SSE comments (keep-alives) and are dropped."""
    assert parse_frame(b":keepalive") is None
    # A comment paired with a real data line still yields the data event.
    frame = b':keepalive\ndata: {"type": "delta", "content": "ok"}'
    assert parse_frame(frame) == {"type": "delta", "content": "ok"}


def test_parse_frame_non_object_json_returns_none() -> None:
    """A JSON payload that decodes to a scalar/list isn't a valid chat event."""
    assert parse_frame(b"data: 42") is None
    assert parse_frame(b'data: ["delta"]') is None


@pytest.mark.parametrize("event_type", sorted(KNOWN_EVENT_TYPES - {"done"}))
def test_parse_frame_every_known_event_type(event_type: str) -> None:
    """Each documented router/provider event type round-trips through ``parse_frame``."""
    frame = f'data: {{"type": "{event_type}", "content": "x"}}'.encode()
    assert parse_frame(frame) == {"type": event_type, "content": "x"}


def _make_streaming_client(chunks: list[bytes]) -> httpx.AsyncClient:
    """Build an ``AsyncClient`` whose response body emits ``chunks`` in order."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_chunked_body(chunks),
        )

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _chunked_body(chunks: list[bytes]) -> AsyncIterator[bytes]:
    """Async byte iterable that yields each chunk separately.

    Forces ``aiter_bytes`` to surface the same chunk boundaries the test
    author specified — this is the whole point of the framer tests.
    """
    for chunk in chunks:
        yield chunk


@pytest.mark.anyio
async def test_stream_two_events_in_one_chunk() -> None:
    """Two complete frames packed into a single chunk both decode in order."""
    chunks = [
        b'data: {"type": "delta", "content": "a"}\n\n'
        b'data: {"type": "delta", "content": "b"}\n\n'
        b"data: [DONE]\n\n",
    ]
    client = _make_streaming_client(chunks)
    async with client:
        events = [event async for event in stream_chat_events(client, "POST", "/chat/")]
    assert events == [
        {"type": "delta", "content": "a"},
        {"type": "delta", "content": "b"},
        {"type": "done"},
    ]


@pytest.mark.anyio
async def test_stream_event_split_across_chunks() -> None:
    """A frame whose bytes straddle two chunks is reassembled before decoding."""
    chunks = [
        b'data: {"type": "delta", "con',
        b'tent": "hi"}\n\n',
        b"data: [DONE]\n\n",
    ]
    client = _make_streaming_client(chunks)
    async with client:
        events = [event async for event in stream_chat_events(client, "POST", "/chat/")]
    assert events == [{"type": "delta", "content": "hi"}, {"type": "done"}]


@pytest.mark.anyio
async def test_stream_stops_yielding_after_done() -> None:
    """Events after ``[DONE]`` are dropped — the iterator returns on completion."""
    chunks = [
        b'data: {"type": "delta", "content": "first"}\n\n',
        b"data: [DONE]\n\n",
        b'data: {"type": "delta", "content": "after-done"}\n\n',
    ]
    client = _make_streaming_client(chunks)
    async with client:
        events = [event async for event in stream_chat_events(client, "POST", "/chat/")]
    assert events == [
        {"type": "delta", "content": "first"},
        {"type": "done"},
    ]
