"""Provider-domain exceptions: typed errors for LLM SDK failures.

Each variant maps cleanly to a class of SDK failure that callers want to
react to differently (auth → re-prompt for credentials; rate-limit → wait;
timeout → fail the turn; unsupported-param → drop the param and retry).

The litellm provider's classifier raises one of these; the chat router
boundary translates the type to an HTTP / SSE error payload.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.exceptions import DomainError


class ProviderError(DomainError):
    """Root of provider-domain failures."""


class ProviderAuthError(ProviderError):
    """API key invalid, expired, or missing."""


@dataclass
class ProviderRateLimitError(ProviderError):
    """Provider rejected the request as rate-limited.

    Attributes:
        retry_after: Seconds the caller should wait before retrying, or
            ``None`` when the provider didn't surface a hint.
    """

    retry_after: float | None = None


class ProviderTimeoutError(ProviderError):
    """Provider didn't respond within the configured deadline."""


class ProviderUnsupportedParamError(ProviderError):
    """Provider rejected a parameter we sent (e.g. reasoning_effort on a model that doesn't support it)."""


class ProviderUnknownError(ProviderError):
    """Catch-all when the SDK exception doesn't match a narrower variant."""
