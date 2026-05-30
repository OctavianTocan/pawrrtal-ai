"""Tests for Telegram message chunking (#424).

Covers:
- chunk_html_for_telegram: short input returns one chunk unchanged.
- chunk_html_for_telegram: long input splits at blank-line boundaries.
- chunk_html_for_telegram: falls back to single-newline boundaries.
- chunk_html_for_telegram: hard-cuts when no newline exists in the window.
- chunk_html_for_telegram: every chunk respects ``max_len``.
- safe_send_html: a short message still sends exactly once.
- safe_send_html: a long message lands as multiple sequential sends.
- safe_send_html: continuation chunks drop the ``reply_to_message_id``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.channels.telegram.delivery import (
    MAX_MESSAGE_LEN,
    chunk_html_for_telegram,
    safe_send_html,
)


def _make_bot() -> AsyncMock:
    """Bot stub whose ``send_message`` returns a deterministic message_id."""
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=99))
    return bot


# ---------------------------------------------------------------------------
# chunk_html_for_telegram — pure helper
# ---------------------------------------------------------------------------


def test_short_input_returns_single_chunk_unchanged() -> None:
    """A message under the limit must round-trip as exactly one chunk."""
    assert chunk_html_for_telegram("hello", max_len=4096) == ["hello"]


def test_splits_on_blank_line_boundary_when_available() -> None:
    """When the input has paragraph breaks, the split honours them."""
    payload = "para-one" + ("a" * 50) + "\n\n" + "para-two" + ("b" * 50)
    chunks = chunk_html_for_telegram(payload, max_len=70)
    assert len(chunks) == 2
    assert chunks[0].endswith("a" * 50)
    assert chunks[1].startswith("para-two")
    # The blank-line separator must not leak into either chunk.
    assert "\n\n" not in chunks[0]
    assert not chunks[1].startswith("\n")


def test_falls_back_to_single_newline_boundary() -> None:
    """Without blank lines, the splitter uses the nearest newline."""
    payload = "alpha" + ("x" * 40) + "\n" + "beta" + ("y" * 40)
    chunks = chunk_html_for_telegram(payload, max_len=50)
    assert len(chunks) == 2
    # The boundary chosen is the newline; neither chunk owns it.
    assert chunks[0].endswith("x" * 40)
    assert chunks[1].startswith("beta")


def test_hard_cuts_when_no_newline_in_window() -> None:
    """A single oversized line is hard-cut at ``max_len``."""
    payload = "z" * 200
    chunks = chunk_html_for_telegram(payload, max_len=80)
    assert all(len(c) <= 80 for c in chunks)
    # Reconstruction is lossless when we're force-cutting (no separators
    # consumed) — important for code blocks the model emits inline.
    assert "".join(chunks) == payload


def test_every_chunk_respects_max_len() -> None:
    """No chunk may exceed the configured limit, regardless of input."""
    payload = ("paragraph " * 50 + "\n\n") * 20
    chunks = chunk_html_for_telegram(payload, max_len=200)
    assert chunks
    assert all(len(c) <= 200 for c in chunks)


def test_chunk_preserves_pre_balance_on_long_block() -> None:
    """A single ``<pre>`` block longer than ``max_len`` must not leave any
    chunk with an unbalanced ``<pre>``/``</pre>`` pair.

    Telegram parses each ``sendMessage`` body independently and returns
    HTTP 400 on an unmatched opening tag — the chunker must close at the
    boundary and re-open in the next chunk so every chunk renders.
    """
    inner = ("line " + ("x" * 30) + "\n") * 200  # ~6.6 KB of code
    payload = f"<pre>{inner}</pre>"
    chunks = chunk_html_for_telegram(payload, max_len=1000)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.count("<pre>") == chunk.count("</pre>"), (
            "every chunk must have balanced <pre>/</pre> tags"
        )
        assert chunk.count("<code>") == chunk.count("</code>"), (
            "every chunk must have balanced <code>/</code> tags"
        )
        assert len(chunk) <= 1000, "rebalance must not exceed max_len"


def test_chunk_html_does_not_split_mid_open_tag() -> None:
    """A long ``<pre>`` near a chunk boundary must not produce a chunk
    that ends with an unclosed ``<pre>`` opening.

    Constructed so the natural split point lands inside the open ``<pre>``
    block — the rebalance pass must close+reopen, not pass it through
    verbatim.
    """
    prelude = "prelude\n\n"
    pre_body = ("code-line-" + ("z" * 20) + "\n") * 60
    payload = prelude + f"<pre>{pre_body}</pre>" + "\n\ntail"
    chunks = chunk_html_for_telegram(payload, max_len=600)
    assert len(chunks) >= 2
    for chunk in chunks:
        # Balanced tag count is the load-bearing assertion — Telegram only
        # cares that every chunk parses as valid HTML.
        assert chunk.count("<pre>") == chunk.count("</pre>")
        assert chunk.count("<code>") == chunk.count("</code>")
        assert len(chunk) <= 600


def test_default_max_len_matches_telegram_limit() -> None:
    """Default applies Telegram's documented 4096 ``sendMessage`` cap."""
    # Input below the limit short-circuits; build one just above it to
    # confirm splitting fires under the default arg.
    payload = "a" * (MAX_MESSAGE_LEN + 100) + "\n\n" + "b" * 50
    chunks = chunk_html_for_telegram(payload)
    assert len(chunks) >= 2
    assert all(len(c) <= MAX_MESSAGE_LEN for c in chunks)


# ---------------------------------------------------------------------------
# safe_send_html — integration with the chunker
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_safe_send_html_short_message_sends_once() -> None:
    """A short payload still issues a single ``send_message`` call."""
    bot = _make_bot()
    await safe_send_html(
        bot,
        chat_id=1,
        html="short",
        reply_to_message_id=None,
        message_thread_id=None,
    )
    assert bot.send_message.await_count == 1


@pytest.mark.anyio
async def test_safe_send_html_long_message_sends_multiple_chunks() -> None:
    """A long payload becomes several sequential ``send_message`` calls."""
    bot = _make_bot()
    payload = ("p" * 4000 + "\n\n") * 3  # ≈ 12k chars across 3 paragraphs
    await safe_send_html(
        bot,
        chat_id=1,
        html=payload,
        reply_to_message_id=None,
        message_thread_id=None,
    )
    assert bot.send_message.await_count >= 3


@pytest.mark.anyio
async def test_safe_send_html_only_first_chunk_replies_to_anchor() -> None:
    """Continuation chunks must not carry the original reply anchor.

    Each chunk is a continuation, not a separate reply — only the first
    one anchors to the user message so the chain reads naturally.
    """
    bot = _make_bot()
    payload = ("z" * 4000 + "\n\n") * 2
    await safe_send_html(
        bot,
        chat_id=1,
        html=payload,
        reply_to_message_id=42,
        message_thread_id=None,
    )
    calls = bot.send_message.await_args_list
    assert len(calls) >= 2
    first_kwargs = calls[0].kwargs
    second_kwargs = calls[1].kwargs
    assert "reply_parameters" in first_kwargs
    assert "reply_parameters" not in second_kwargs


@pytest.mark.anyio
async def test_safe_send_html_returns_first_chunk_message_id() -> None:
    """Existing callers pin/edit/delete the first chunk's ID — keep returning it."""
    bot = AsyncMock()
    bot.send_message = AsyncMock(
        side_effect=[
            SimpleNamespace(message_id=100),
            SimpleNamespace(message_id=101),
            SimpleNamespace(message_id=102),
        ]
    )
    payload = ("q" * 4000 + "\n\n") * 3
    first_id = await safe_send_html(
        bot,
        chat_id=1,
        html=payload,
        reply_to_message_id=None,
        message_thread_id=None,
    )
    assert first_id == 100
