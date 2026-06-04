"""Service-account auth for the Google Chat channel.

Mints a single OAuth2 access token (cached, refreshed on expiry) scoped
for both the Chat REST API and Pub/Sub pull/ack. Uses ``google-auth``
(already a dependency) + ``httpx`` so the channel needs no extra
packages — mirroring the credential-light approach in
:mod:`app.providers.agy_api`.

This module never logs token values.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .settings import google_chat_settings

if TYPE_CHECKING:
    from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# One token, both APIs: the Chat REST surface (create/patch messages) and
# the Pub/Sub pull/ack surface that feeds inbound events. Requesting both
# scopes up front means the cached token works for every call the channel
# makes, so there is only one refresh path to reason about.
_SCOPES = (
    "https://www.googleapis.com/auth/chat.bot",
    "https://www.googleapis.com/auth/pubsub",
)


class GoogleChatAuthError(RuntimeError):
    """Raised when the Google Chat service-account auth is unusable."""


@dataclass
class _CredentialsCache:
    """Holds the lazily-loaded service-account credentials.

    A tiny mutable singleton (same shape as the agy_api HTTP client
    cache) so the access token is minted once and refreshed in place,
    without a module-level ``global``.
    """

    creds: Credentials | None = None


_CACHE = _CredentialsCache()
_refresh_lock = asyncio.Lock()


def has_google_chat_auth() -> bool:
    """Return whether the channel has enough config to run.

    The channel needs the service-account file plus the Pub/Sub project
    and subscription that deliver inbound events; any missing piece
    disables the whole channel (mirrors Telegram's ``telegram_bot_token``
    gate).
    """
    return bool(
        google_chat_settings.google_chat_service_account_file
        and google_chat_settings.google_chat_project_id
        and google_chat_settings.google_chat_subscription_id
    )


def _load_credentials() -> Credentials:
    """Load scoped service-account credentials from the configured file."""
    # Local import keeps the google-auth dependency off the hot path when
    # the channel is disabled (the common case for most deployments).
    from google.oauth2 import service_account  # noqa: PLC0415

    path = google_chat_settings.google_chat_service_account_file
    if not path:
        raise GoogleChatAuthError("GOOGLE_CHAT_SERVICE_ACCOUNT_FILE is not configured.")
    try:
        return service_account.Credentials.from_service_account_file(path, scopes=list(_SCOPES))
    except (OSError, ValueError) as exc:
        raise GoogleChatAuthError(f"Could not load Google Chat service account: {exc}") from exc


async def get_access_token() -> str:
    """Return a valid bearer token, refreshing through google-auth on expiry.

    The credentials object is cached and reused; ``refresh`` is blocking
    (it hits Google's OAuth token endpoint), so it runs in a worker
    thread to avoid stalling the event loop. The lock collapses
    concurrent callers onto a single refresh.
    """
    from google.auth.transport.requests import Request  # noqa: PLC0415

    async with _refresh_lock:
        if _CACHE.creds is None:
            _CACHE.creds = _load_credentials()
        creds: Any = _CACHE.creds
        if not creds.valid:
            try:
                await asyncio.to_thread(creds.refresh, Request())
            except Exception as exc:  # google-auth raises a broad RefreshError tree
                raise GoogleChatAuthError(f"Google Chat token refresh failed: {exc}") from exc
        token = creds.token
    if not token:
        raise GoogleChatAuthError("Google Chat token refresh returned no token.")
    return str(token)
