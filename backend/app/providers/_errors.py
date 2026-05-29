"""Typed provider failure shapes.

Closed set of provider-seam failure modes that the LiteLLM stream opener
(and any other provider that migrates) raises on connection / setup
failure. Errors raised *inside* a stream after a successful open
continue to surface raw — the chat router classifies those into
``StreamEvent(type="error")`` frames.

Was originally introduced as a discriminated union of ``@dataclass``
shapes for the returns pilot. With the pilot wound down, the failure
modes are now Exception subclasses so callers can use the standard
``try/except`` machinery; the carried fields (``param``, ``model``,
``retry_after``) are preserved for the existing classifier logic.
"""

from __future__ import annotations

from app.exceptions import DomainError


class ProviderError(DomainError):
    """Root of the closed set of provider-seam failures."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class ProviderAuthError(ProviderError):
    """Upstream rejected the call as unauthenticated/forbidden (HTTP 401/403)."""


class ProviderRateLimitError(ProviderError):
    """Upstream rate-limited the call (HTTP 429).

    Attributes:
        retry_after: Seconds the upstream suggested waiting before
            retrying, when the SDK surfaces a ``Retry-After`` header;
            ``None`` if the SDK did not expose one.
    """

    def __init__(self, message: str = "", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderUnsupportedParamError(ProviderError):
    """A request parameter is not supported by this model/provider.

    Typical cause: a stored ``reasoning_effort`` value forwarded to a
    non-reasoning model. ``param`` and ``model`` let the caller surface
    a precise UI hint without parsing the message.
    """

    def __init__(self, message: str = "", param: str = "", model: str = "") -> None:
        super().__init__(message)
        self.param = param
        self.model = model


class ProviderTimeoutError(ProviderError):
    """Connection or read deadline exceeded before any stream chunks arrived."""


class ProviderUnknownError(ProviderError):
    """Fallback bucket for failures the classifier did not recognise.

    Carries the original message verbatim so the caller can still log
    something useful while the closed set above grows over time.
    """
