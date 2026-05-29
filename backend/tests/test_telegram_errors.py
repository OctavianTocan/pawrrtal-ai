"""Tests for telegram_errors — typed HTML error cards and classifier.

Covers:
- Each of the 9 card types renders expected structure (icon, title, body, recoveries).
- ``render_error_card`` dispatches to the correct renderer.
- ``classify_error`` maps known error_codes to the right ``ErrorKind``.
- ``classify_error`` maps exception types to the right ``ErrorKind``.
- Unknown codes/exceptions fall back to ``PROVIDER_ERROR``.
- HTML special characters in ``detail`` are escaped.
"""

from __future__ import annotations

from typing import cast

import pytest

from app.channels.telegram.errors import (
    ErrorKind,
    classify_error,
    render_agent_terminated_card,
    render_auth_error_card,
    render_connection_card,
    render_empty_stream_card,
    render_error_card,
    render_provider_error_card,
    render_provider_overloaded_card,
    render_rate_limit_card,
    render_timeout_card,
    render_unknown_model_card,
)
from app.core.providers.base import StreamEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_structure(card: str) -> None:
    """Assert the card has the standard structural elements."""
    assert "<b>" in card
    assert "What you can do:" in card
    assert "•" in card


# ---------------------------------------------------------------------------
# Individual card renderers
# ---------------------------------------------------------------------------


class TestRenderTimeoutCard:
    def test_contains_icon_and_title(self) -> None:
        card = render_timeout_card()
        assert "⏰" in card
        assert "Took too long" in card

    def test_standard_structure(self) -> None:
        _has_structure(render_timeout_card())

    def test_detail_embedded_in_body(self) -> None:
        card = render_timeout_card("context window full")
        assert "context window full" in card

    def test_html_special_chars_escaped(self) -> None:
        # detail is html.escape()d inside the card; the raw tag must not appear.
        card = render_timeout_card("<script>")
        assert "<script>" not in card
        # After escaping, the angle brackets appear as &lt; / &gt;
        assert "&lt;" in card

    def test_recovery_mentions_slash_new(self) -> None:
        card = render_timeout_card()
        assert "/new" in card


class TestRenderProviderOverloadedCard:
    def test_contains_icon_and_title(self) -> None:
        card = render_provider_overloaded_card()
        assert "🏗️" in card
        assert "overloaded" in card.lower()

    def test_standard_structure(self) -> None:
        _has_structure(render_provider_overloaded_card())


class TestRenderAuthErrorCard:
    def test_contains_icon_and_title(self) -> None:
        card = render_auth_error_card()
        assert "🔑" in card
        assert "Authentication" in card

    def test_standard_structure(self) -> None:
        _has_structure(render_auth_error_card())

    def test_recovery_mentions_admin(self) -> None:
        card = render_auth_error_card()
        assert "admin" in card.lower()


class TestRenderRateLimitCard:
    def test_contains_icon_and_title(self) -> None:
        card = render_rate_limit_card()
        assert "🚦" in card
        assert "Rate limited" in card

    def test_standard_structure(self) -> None:
        _has_structure(render_rate_limit_card())

    def test_recovery_mentions_status(self) -> None:
        card = render_rate_limit_card()
        assert "/status" in card


class TestRenderEmptyStreamCard:
    def test_contains_icon_and_title(self) -> None:
        card = render_empty_stream_card()
        assert "⚠️" in card
        assert "reply" in card.lower()

    def test_standard_structure(self) -> None:
        _has_structure(render_empty_stream_card())


class TestRenderAgentTerminatedCard:
    def test_contains_icon_and_title(self) -> None:
        card = render_agent_terminated_card("max_iterations")
        assert "⚠️" in card
        assert "stopped early" in card.lower()

    def test_detail_in_body(self) -> None:
        card = render_agent_terminated_card("hit max_iterations cap of 25")
        assert "max_iterations" in card

    def test_html_special_chars_escaped(self) -> None:
        card = render_agent_terminated_card("<bad>")
        assert "<bad>" not in card
        assert "&lt;" in card


class TestRenderConnectionCard:
    def test_contains_icon_and_title(self) -> None:
        card = render_connection_card()
        assert "🌐" in card
        assert "Connection" in card

    def test_standard_structure(self) -> None:
        _has_structure(render_connection_card())


class TestRenderUnknownModelCard:
    def test_contains_icon_and_title(self) -> None:
        card = render_unknown_model_card()
        assert "🤷" in card
        assert "Unknown model" in card

    def test_recovery_mentions_models_command(self) -> None:
        card = render_unknown_model_card()
        assert "/models" in card

    def test_standard_structure(self) -> None:
        _has_structure(render_unknown_model_card())


class TestRenderProviderErrorCard:
    def test_contains_icon_and_title(self) -> None:
        card = render_provider_error_card()
        assert "❌" in card
        assert "Provider error" in card

    def test_standard_structure(self) -> None:
        _has_structure(render_provider_error_card())


# ---------------------------------------------------------------------------
# render_error_card dispatcher
# ---------------------------------------------------------------------------


class TestRenderErrorCard:
    @pytest.mark.parametrize(
        ("kind", "expected_icon"),
        [
            (ErrorKind.TIMEOUT, "⏰"),
            (ErrorKind.PROVIDER_OVERLOADED, "🏗️"),
            (ErrorKind.AUTH_ERROR, "🔑"),
            (ErrorKind.RATE_LIMIT, "🚦"),
            (ErrorKind.EMPTY_STREAM, "⚠️"),
            (ErrorKind.AGENT_TERMINATED, "⚠️"),
            (ErrorKind.CONNECTION, "🌐"),
            (ErrorKind.UNKNOWN_MODEL, "🤷"),
            (ErrorKind.PROVIDER_ERROR, "❌"),
        ],
    )
    def test_dispatches_correct_card(self, kind: ErrorKind, expected_icon: str) -> None:
        card = render_error_card(kind, "some detail")
        assert expected_icon in card

    def test_detail_forwarded(self) -> None:
        card = render_error_card(ErrorKind.TIMEOUT, "context full")
        assert "context full" in card


# ---------------------------------------------------------------------------
# classify_error — StreamEvent dict
# ---------------------------------------------------------------------------


class TestClassifyErrorEvent:
    def test_timeout_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "timeout"}))
            == ErrorKind.TIMEOUT
        )

    def test_request_timeout_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "request_timeout"}))
            == ErrorKind.TIMEOUT
        )

    def test_overloaded_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "overloaded"}))
            == ErrorKind.PROVIDER_OVERLOADED
        )

    def test_auth_error_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "auth_error"}))
            == ErrorKind.AUTH_ERROR
        )

    def test_invalid_api_key_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "invalid_api_key"}))
            == ErrorKind.AUTH_ERROR
        )

    def test_rate_limit_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "rate_limit"}))
            == ErrorKind.RATE_LIMIT
        )

    def test_too_many_requests_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "too_many_requests"}))
            == ErrorKind.RATE_LIMIT
        )

    def test_empty_stream_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "empty_stream"}))
            == ErrorKind.EMPTY_STREAM
        )

    def test_agent_terminated_via_type(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "agent_terminated", "content": "max iter"}))
            == ErrorKind.AGENT_TERMINATED
        )

    def test_agent_terminated_via_error_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "agent_terminated"}))
            == ErrorKind.AGENT_TERMINATED
        )

    def test_connection_error_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "connection_error"}))
            == ErrorKind.CONNECTION
        )

    def test_unknown_model_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "unknown_model"}))
            == ErrorKind.UNKNOWN_MODEL
        )

    def test_model_not_found_code(self) -> None:
        assert (
            classify_error(cast(StreamEvent, {"type": "error", "error_code": "model_not_found"}))
            == ErrorKind.UNKNOWN_MODEL
        )

    def test_unknown_code_falls_back_to_provider_error(self) -> None:
        assert (
            classify_error(
                cast(StreamEvent, {"type": "error", "error_code": "totally_unknown_xyz"})
            )
            == ErrorKind.PROVIDER_ERROR
        )

    def test_no_error_code_falls_back_to_provider_error(self) -> None:
        assert classify_error(cast(StreamEvent, {"type": "error"})) == ErrorKind.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# classify_error — exception instances
# ---------------------------------------------------------------------------


class TestClassifyErrorException:
    def test_timeout_exception(self) -> None:
        class _TimeoutError(Exception):
            pass

        assert classify_error(_TimeoutError("too slow")) == ErrorKind.TIMEOUT

    def test_connection_error_exception(self) -> None:
        class _ConnectionError(Exception):
            pass

        assert classify_error(_ConnectionError("refused")) == ErrorKind.CONNECTION

    def test_network_error_exception(self) -> None:
        class NetworkError(Exception):
            pass

        assert classify_error(NetworkError("unreachable")) == ErrorKind.CONNECTION

    def test_rate_limit_exception(self) -> None:
        class RateLimitError(Exception):
            pass

        assert classify_error(RateLimitError("429")) == ErrorKind.RATE_LIMIT

    def test_unknown_exception_falls_back_to_provider_error(self) -> None:
        assert classify_error(ValueError("something weird")) == ErrorKind.PROVIDER_ERROR
