"""Typed HTML error cards for Telegram delivery.

Each card follows the structure::

    {icon} <b>{Error Type}</b>

    {message}

    <b>What you can do:</b>
    • {recovery 1}
    • {recovery 2}
    • {recovery 3}

All user-visible text is HTML-escaped before embedding.  The card functions
return pre-rendered Telegram HTML strings ready for ``safe_send_html``.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.providers.base import StreamEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error kind enumeration
# ---------------------------------------------------------------------------


class ErrorKind(StrEnum):
    """Canonical categories surfaced as typed error cards."""

    TIMEOUT = "timeout"
    PROVIDER_OVERLOADED = "provider_overloaded"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    EMPTY_STREAM = "empty_stream"
    AGENT_TERMINATED = "agent_terminated"
    CONNECTION = "connection"
    UNKNOWN_MODEL = "unknown_model"
    PROVIDER_ERROR = "provider_error"


# ---------------------------------------------------------------------------
# Internal card builder
# ---------------------------------------------------------------------------

_BULLET = "\n• "


def _build_card(icon: str, title: str, body: str, recoveries: list[str]) -> str:
    """Assemble the standard error card HTML.

    The card functions that call this must pass already-escaped ``body``
    strings.  ``title`` and each ``recovery`` item are escaped here since
    they are static strings defined in this module (no double-escape risk).

    Args:
        icon: Single glyph/emoji shown before the title.
        title: Bold error type heading (will be HTML-escaped here).
        body: Main explanatory sentence — **callers must escape user/provider
              content before embedding it**; this string is written as-is.
        recoveries: Recovery suggestions (each will be HTML-escaped here).

    Returns:
        Telegram HTML string.
    """
    esc_title = html.escape(title)
    recovery_items = _BULLET.join(html.escape(r) for r in recoveries)
    return f"{icon} <b>{esc_title}</b>\n\n{body}\n\n<b>What you can do:</b>\n• {recovery_items}"


# ---------------------------------------------------------------------------
# Card render functions — one per ErrorKind
# ---------------------------------------------------------------------------


def render_timeout_card(detail: str = "") -> str:
    """⏰ Timeout — the turn took too long."""
    extra = f": {html.escape(detail.strip())}" if detail.strip() else "."
    body = f"The request timed out{extra}"
    return _build_card(
        "⏰",
        "Took too long",
        body,
        [
            "Try a shorter or simpler prompt",
            "Start fresh with /new",
            "Try again — transient timeouts usually resolve quickly",
        ],
    )


def render_provider_overloaded_card(detail: str = "") -> str:
    """🏗️ Provider overloaded."""
    extra = f" ({html.escape(detail.strip())})" if detail.strip() else ""
    body = f"The AI provider is currently overloaded{extra}."
    return _build_card(
        "🏗️",
        "Provider overloaded",
        body,
        [
            "Wait a moment and try again",
            "Switch to a smaller/faster model with /model",
            "Start fresh with /new",
        ],
    )


def render_auth_error_card(detail: str = "") -> str:
    """🔑 Authentication issue."""
    extra = f" ({html.escape(detail.strip())})" if detail.strip() else ""
    body = f"There is an authentication problem with the provider{extra}."
    return _build_card(
        "🔑",
        "Authentication issue",
        body,
        [
            "Contact the admin — the API key may have expired",
            "Reconnect your account on web settings",
            "Try again in a few minutes",
        ],
    )


def render_rate_limit_card(detail: str = "") -> str:
    """🚦 Rate limited."""
    extra = f" ({html.escape(detail.strip())})" if detail.strip() else ""
    body = f"You have been rate-limited by the provider{extra}."
    return _build_card(
        "🚦",
        "Rate limited",
        body,
        [
            "Wait a moment before sending another message",
            "Use /status to check current limits",
            "Try again shortly",
        ],
    )


def render_empty_stream_card(detail: str = "") -> str:
    """⚠️ The agent finished without producing a reply."""
    extra = f" ({html.escape(detail.strip())})" if detail.strip() else ""
    body = f"The agent finished without producing a reply{extra}."
    return _build_card(
        "⚠️",
        "No reply produced",
        body,
        [
            "Rephrase your message and try again",
            "Start fresh with /new",
            "Try a different model with /model",
        ],
    )


def render_agent_terminated_card(detail: str = "") -> str:
    """⚠️ Agent stopped early."""
    esc_detail = html.escape(detail.strip()) if detail.strip() else "unknown reason"
    body = f"The agent stopped early: {esc_detail}."
    return _build_card(
        "⚠️",
        "Agent stopped early",
        body,
        [
            "Try again — this is usually transient",
            "Check /status for more detail",
            "Start fresh with /new if the problem persists",
        ],
    )


def render_connection_card(detail: str = "") -> str:
    """🌐 Connection issue."""
    extra = f" ({html.escape(detail.strip())})" if detail.strip() else ""
    body = f"A connection problem occurred while contacting the provider{extra}."
    return _build_card(
        "🌐",
        "Connection issue",
        body,
        [
            "Try again — network glitches are usually transient",
            "Check /status to see gateway health",
            "Contact the admin if the problem persists",
        ],
    )


def render_unknown_model_card(detail: str = "") -> str:
    """🤷 Unknown model."""
    extra = f" ({html.escape(detail.strip())})" if detail.strip() else ""
    body = f"The requested model is not available{extra}."
    return _build_card(
        "🤷",
        "Unknown model",
        body,
        [
            "Pick a model from /models",
            "Set one explicitly with /model <id>",
            "Start fresh with /new to use the default",
        ],
    )


def render_provider_error_card(detail: str = "") -> str:
    """❌ Generic provider error."""
    extra = f" ({html.escape(detail.strip())})" if detail.strip() else ""
    body = f"The AI provider returned an error{extra}."
    return _build_card(
        "❌",
        "Provider error",
        body,
        [
            "Try again — this is often transient",
            "Start fresh with /new",
            "Check /status for gateway health",
        ],
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_CARD_RENDERERS: dict[ErrorKind, Callable[[str], str]] = {
    ErrorKind.TIMEOUT: render_timeout_card,
    ErrorKind.PROVIDER_OVERLOADED: render_provider_overloaded_card,
    ErrorKind.AUTH_ERROR: render_auth_error_card,
    ErrorKind.RATE_LIMIT: render_rate_limit_card,
    ErrorKind.EMPTY_STREAM: render_empty_stream_card,
    ErrorKind.AGENT_TERMINATED: render_agent_terminated_card,
    ErrorKind.CONNECTION: render_connection_card,
    ErrorKind.UNKNOWN_MODEL: render_unknown_model_card,
    ErrorKind.PROVIDER_ERROR: render_provider_error_card,
}


def render_error_card(kind: ErrorKind, detail: str = "") -> str:
    """Render the typed error card HTML for ``kind`` with optional ``detail``.

    Args:
        kind: The error category.
        detail: Optional extra context to embed in the card body.

    Returns:
        Telegram HTML string ready to pass to ``safe_send_html``.
    """
    renderer = _CARD_RENDERERS.get(kind, render_provider_error_card)
    return renderer(detail)


# ---------------------------------------------------------------------------
# Error classifier
# ---------------------------------------------------------------------------

# Error code → ErrorKind mappings.  These values come from
# ``StreamEvent["error_code"]`` as emitted by the provider layer.
_ERROR_CODE_MAP: dict[str, ErrorKind] = {
    "timeout": ErrorKind.TIMEOUT,
    "request_timeout": ErrorKind.TIMEOUT,
    "overloaded": ErrorKind.PROVIDER_OVERLOADED,
    "provider_overloaded": ErrorKind.PROVIDER_OVERLOADED,
    "server_overloaded": ErrorKind.PROVIDER_OVERLOADED,
    "auth_error": ErrorKind.AUTH_ERROR,
    "authentication_error": ErrorKind.AUTH_ERROR,
    "invalid_api_key": ErrorKind.AUTH_ERROR,
    "rate_limit": ErrorKind.RATE_LIMIT,
    "rate_limit_exceeded": ErrorKind.RATE_LIMIT,
    "too_many_requests": ErrorKind.RATE_LIMIT,
    "empty_stream": ErrorKind.EMPTY_STREAM,
    "no_reply": ErrorKind.EMPTY_STREAM,
    "agent_terminated": ErrorKind.AGENT_TERMINATED,
    "connection": ErrorKind.CONNECTION,
    "connection_error": ErrorKind.CONNECTION,
    "network_error": ErrorKind.CONNECTION,
    "unknown_model": ErrorKind.UNKNOWN_MODEL,
    "model_not_found": ErrorKind.UNKNOWN_MODEL,
}

# Exception type name substrings → ErrorKind.  Matched case-insensitively.
_EXCEPTION_TYPE_MAP: dict[str, ErrorKind] = {
    "timeout": ErrorKind.TIMEOUT,
    "overloaded": ErrorKind.PROVIDER_OVERLOADED,
    "authenticationerror": ErrorKind.AUTH_ERROR,
    "ratelimit": ErrorKind.RATE_LIMIT,
    "connectionerror": ErrorKind.CONNECTION,
    "networkerror": ErrorKind.CONNECTION,
}


def classify_error(event_or_exception: StreamEvent | BaseException) -> ErrorKind:
    """Map a ``StreamEvent`` or exception to an ``ErrorKind``.

    Uses ``error_code`` on stream events, then falls back to heuristic
    matching on the exception type name. Returns ``PROVIDER_ERROR`` when
    no mapping is found.

    Args:
        event_or_exception: A ``StreamEvent`` dict or an exception instance.

    Returns:
        The closest matching ``ErrorKind``.
    """
    if isinstance(event_or_exception, dict):
        code = str(event_or_exception.get("error_code") or "").lower().strip()
        if code:
            kind = _ERROR_CODE_MAP.get(code)
            if kind is not None:
                return kind
        # Also try matching on the event type for agent_terminated
        etype = str(event_or_exception.get("type") or "").lower()
        if etype == "agent_terminated":
            return ErrorKind.AGENT_TERMINATED
        return ErrorKind.PROVIDER_ERROR

    # Exception instance — match on type name
    type_name = type(event_or_exception).__name__.lower()
    for substr, kind in _EXCEPTION_TYPE_MAP.items():
        if substr in type_name:
            return kind
    return ErrorKind.PROVIDER_ERROR
