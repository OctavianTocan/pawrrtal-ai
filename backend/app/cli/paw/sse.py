r"""SSE stream consumer for paw.

Mirrors the frontend's technique (``fetch`` + ``ReadableStream.getReader()`` +
``TextDecoderStream`` + manual ``\n\n`` framing) — see
``frontend/features/chat/hooks/use-chat.ts:165`` for the canonical implementation.
The chat endpoint emits a custom SSE shape: one JSON dict per ``data:`` line,
terminated by the literal ``data: [DONE]\n\n`` sentinel. A byte-level framer
(rather than ``httpx-sse``) keeps the CLI's parser reproducing the same
frame-boundary semantics the frontend exercises, so frame-boundary bugs are
visible in both surfaces.

Event taxonomy (as of 2026-05-27, mined from
``backend/app/api/chat.py`` and ``backend/app/core/providers/*/events.py``):

* ``delta``           — provider-native text chunk
* ``thinking``        — provider-native reasoning content
* ``tool_use``        — provider-native tool invocation
* ``tool_progress``   — provider-native non-terminal tool progress
* ``tool_result``     — provider-native tool result
* ``artifact``        — router-injected (``chat.py:105``) + ``openai_codex/events.py:132``
* ``usage``           — provider-native token usage (e.g. ``openai_codex/events.py:154``)
* ``error``           — stream-level error
* ``message``         — router-injected at ``backend/app/api/chat.py:309`` (``send_message`` tool)
* ``done``            — synthesized here from the ``[DONE]`` sentinel
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FRAME_DELIMITER = b"\n\n"
DONE_SENTINEL = "[DONE]"
DATA_PREFIX = "data:"
COMMENT_PREFIX = ":"

# Type alias for the optional raw-frame tap used by `paw record` to capture
# the wire bytes of an SSE stream alongside the structured HTTP record.
RawFrameTap = Callable[[bytes], None]

KNOWN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "delta",
        "thinking",
        "tool_use",
        "tool_progress",
        "tool_result",
        "artifact",
        "usage",
        "error",
        "message",
        # Controlled stop from the agent loop's safety layer
        # (iteration cap, wall-clock budget, consecutive-error
        # threshold). Distinct from "error" so renderers can show a
        # neutral "stopped" affordance instead of a failure banner.
        "agent_terminated",
        "done",
    }
)


def parse_frame(frame: bytes) -> dict[str, Any] | None:
    r"""Decode one SSE frame (the bytes between two ``\n\n`` delimiters).

    Returns ``None`` for empty frames, comment-only frames, and frames whose
    ``data:`` payload is not valid JSON (incomplete or malformed chunks).
    Returns ``{"type": "done"}`` for the ``[DONE]`` sentinel so callers can
    treat completion as just another event in the iterator.
    """
    text = frame.decode("utf-8", errors="replace").strip()
    if not text:
        return None

    payload_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith(DATA_PREFIX):
            payload_lines.append(line[len(DATA_PREFIX) :].lstrip())
            continue
        if line.startswith(COMMENT_PREFIX):
            # SSE comment ("`:keepalive`"); intentionally ignored.
            continue
        # Other SSE field lines (``event:``, ``id:``, ``retry:``) are not
        # used by the chat endpoint, so we drop them rather than silently
        # treating them as data.

    if not payload_lines:
        return None

    payload = "\n".join(payload_lines)
    if payload == DONE_SENTINEL:
        return {"type": "done"}

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(decoded, dict):
        return None
    return decoded


async def stream_chat_events(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json_body: Any | None = None,
    on_raw_frame: RawFrameTap | None = None,
) -> AsyncIterator[dict[str, Any]]:
    r"""Yield decoded chat events from an SSE endpoint (``POST /api/v1/chat/``).

    Buffers raw bytes and splits on the ``\n\n`` frame delimiter so frames
    that arrive split across chunks are reassembled before decoding. Stops
    yielding after a ``{"type": "done"}`` event is produced — callers that
    want to drive the stream further should not rely on the iterator
    resuming past completion.

    ``on_raw_frame``, when provided, is invoked with the raw bytes of every
    non-empty frame *before* decoding — this is how `paw record` captures
    the wire stream (comments, malformed frames, the ``[DONE]`` sentinel,
    everything). It is purely additive: tap failures must not perturb the
    consumer. The tap call is wrapped via ``_safe_invoke_tap`` so a buggy
    caller-supplied callback can't break the SSE iterator.
    """
    async with client.stream(method, path, json=json_body) as resp:
        resp.raise_for_status()
        buffer = b""
        async for chunk in resp.aiter_bytes():
            buffer += chunk
            while FRAME_DELIMITER in buffer:
                frame, buffer = buffer.split(FRAME_DELIMITER, 1)
                if on_raw_frame is not None and frame.strip():
                    _safe_invoke_tap(on_raw_frame, frame)
                event = parse_frame(frame)
                if event is None:
                    continue
                yield event
                if event.get("type") == "done":
                    return
        # Trailing frame without a ``\n\n`` terminator: still attempt a decode
        # so a server that closes the connection cleanly without the final
        # delimiter doesn't silently drop its last event.
        if buffer.strip():
            if on_raw_frame is not None:
                _safe_invoke_tap(on_raw_frame, buffer)
            event = parse_frame(buffer)
            if event is not None:
                yield event


def _safe_invoke_tap(tap: RawFrameTap, frame: bytes) -> None:
    """Invoke ``tap(frame)`` and log-but-swallow any exception it raises.

    The tap is caller-supplied (e.g. paw's record file writer) and the
    SSE consumer's contract guarantees tap failures must not perturb the
    stream. A broad ``except Exception`` is intentional here because the
    callback is user code with unknown failure modes (filesystem errors,
    serialization bugs, etc.) and the surrounding loop has no recovery
    path for them beyond "keep iterating."
    """
    try:
        tap(frame)
    except Exception as exc:
        logger.warning("SSE raw-frame tap raised: %s", exc, exc_info=True)
