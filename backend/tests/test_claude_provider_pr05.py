"""Unit tests for the new Claude provider helpers landed in PR 05.

Targets the pure-function helpers (retry classification, backoff,
multimodal prompt assembly) — the actual SDK call path is exercised
by the existing ``test_claude_provider.py`` integration tests.
"""

from __future__ import annotations

import pytest

from app.providers.claude.provider import (
    _aiter_user_prompt,
    _is_retryable_cli_connection,
    _retry_backoff_seconds,
)

pytestmark = pytest.mark.anyio


class TestRetryClassifier:
    """Plain network errors retry; MCP errors don't."""

    @pytest.mark.parametrize(
        "message",
        [
            "Connection reset by peer",
            "Read timed out",
            "Subprocess closed unexpectedly",
        ],
    )
    def test_plain_connection_errors_retry(self, message: str) -> None:
        assert _is_retryable_cli_connection(RuntimeError(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "MCP server failed to start",
            "mcp__pawrrtal__echo_back not registered",
            "MCP transport closed",
        ],
    )
    def test_mcp_errors_do_not_retry(self, message: str) -> None:
        # Configuration bugs masquerading as connection errors —
        # retry just delays the visible failure.
        assert _is_retryable_cli_connection(RuntimeError(message)) is False


class TestRetryBackoff:
    """Backoff is exponential and bounded."""

    def test_first_attempt_uses_base_delay(self) -> None:
        # Attempt 1 = base * factor^0 = base.
        assert _retry_backoff_seconds(1) > 0

    def test_grows_with_attempt(self) -> None:
        a, b, c = (
            _retry_backoff_seconds(1),
            _retry_backoff_seconds(2),
            _retry_backoff_seconds(3),
        )
        assert a <= b <= c

    def test_capped_at_ceiling(self) -> None:
        # A very high attempt should hit the ceiling, not blow up.
        capped = _retry_backoff_seconds(50)
        assert capped <= 30.0  # _RETRY_SLEEP_CEILING_SECONDS


class TestAiterUserPromptMultimodal:
    """Multimodal images become Claude content blocks."""

    async def test_text_only_unchanged(self) -> None:
        prompts = [p async for p in _aiter_user_prompt("hello")]
        assert len(prompts) == 1
        envelope = prompts[0]
        assert envelope["type"] == "user"
        assert envelope["message"]["role"] == "user"
        assert envelope["message"]["content"] == "hello"

    async def test_with_image_builds_content_blocks(self) -> None:
        prompts = [
            p
            async for p in _aiter_user_prompt(
                "what is this?",
                images=[{"data": "base64here", "media_type": "image/png"}],
            )
        ]
        envelope = prompts[0]
        content = envelope["message"]["content"]
        assert isinstance(content, list)
        # Image block first, text block last.
        assert content[0]["type"] == "image"
        assert content[0]["source"]["data"] == "base64here"
        assert content[0]["source"]["media_type"] == "image/png"
        assert content[-1]["type"] == "text"
        assert content[-1]["text"] == "what is this?"

    async def test_default_media_type_when_missing(self) -> None:
        prompts = [
            p
            async for p in _aiter_user_prompt(
                "x",
                images=[{"data": "abc"}],
            )
        ]
        content = prompts[0]["message"]["content"]
        assert content[0]["source"]["media_type"] == "image/png"

    async def test_image_without_data_is_skipped(self) -> None:
        prompts = [
            p
            async for p in _aiter_user_prompt(
                "y",
                images=[{"media_type": "image/png"}, {"data": "ok"}],
            )
        ]
        content = prompts[0]["message"]["content"]
        # Only one image block survives; text is always present.
        image_blocks = [b for b in content if b.get("type") == "image"]
        assert len(image_blocks) == 1

    async def test_empty_image_list_falls_through_to_text_path(self) -> None:
        prompts = [p async for p in _aiter_user_prompt("hi", images=[])]
        envelope = prompts[0]
        # Empty list → text-only envelope, not a content-block list.
        assert envelope["message"]["content"] == "hi"
