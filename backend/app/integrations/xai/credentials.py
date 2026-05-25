"""Unified xAI credential resolution (#372 implementation 2/N).

The xAI provider + STT route used to call ``resolve_api_key("XAI_API_KEY")``
directly, returning a single long-lived bearer token. With OAuth in
the picture (#372) callers need to:

1. Prefer the OAuth access token when one is stored on the
   workspace (recently authorised via ``/login xai``).
2. Refresh that access token transparently when it's near expiry.
3. Fall back to the legacy long-lived ``XAI_API_KEY`` when no
   OAuth session exists.

:func:`resolve_xai_credentials` is the single helper every xAI
caller funnels through.

Token storage uses the existing encrypted workspace ``.env``
pipeline (``backend/app/core/keys.py``). Three new keys carry the
OAuth state:

- ``XAI_OAUTH_ACCESS_TOKEN``
- ``XAI_OAUTH_REFRESH_TOKEN``
- ``XAI_OAUTH_EXPIRES_AT`` (ISO 8601 UTC)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings
from app.core.keys import load_workspace_env, resolve_api_key, save_workspace_env
from app.integrations.xai.oauth import (
    OAuthError,
    refresh_token,
)

logger = logging.getLogger(__name__)

# Refresh the access token when it's within this many seconds of
# expiring. Tuned so a long-running streaming turn doesn't 401 mid-
# flight on the first request that lands after the token expires.
_REFRESH_LEAD_SECONDS = 60

# The three workspace ``.env`` keys the OAuth flow writes. Lifted
# here so the helper that writes them and the helper that reads
# them stay in sync.
ACCESS_ENV_KEY = "XAI_OAUTH_ACCESS_TOKEN"
REFRESH_ENV_KEY = "XAI_OAUTH_REFRESH_TOKEN"
EXPIRES_AT_ENV_KEY = "XAI_OAUTH_EXPIRES_AT"


async def resolve_xai_credentials(workspace_root: Path | None) -> str | None:
    """Return a bearer token usable for an xAI request, or ``None``.

    Resolution order:

    1. **OAuth access token on the workspace**, refreshed
       transparently when it's near expiry.
    2. **Legacy ``XAI_API_KEY``** on the workspace ``.env``.
    3. **Gateway-global ``settings.xai_api_key``** as the final
       fallback.

    Returns ``None`` only when *none* of the above produced a
    credential — at which point the caller should surface a clear
    "xAI is not configured" error rather than send a 401-bound
    request.
    """
    if workspace_root is not None:
        oauth_token = await _resolve_oauth_token(workspace_root)
        if oauth_token is not None:
            return oauth_token
        workspace_legacy = resolve_api_key(workspace_root, "XAI_API_KEY")
        if workspace_legacy:
            return workspace_legacy
    return settings.xai_api_key or None


async def _resolve_oauth_token(workspace_root: Path) -> str | None:
    """Read the workspace OAuth state and refresh-if-needed."""
    env = load_workspace_env(workspace_root)
    access_token = env.get(ACCESS_ENV_KEY, "").strip()
    refresh_value = env.get(REFRESH_ENV_KEY, "").strip()
    expires_at_raw = env.get(EXPIRES_AT_ENV_KEY, "").strip()

    if not access_token:
        return None

    if not _needs_refresh(expires_at_raw):
        return access_token

    if not refresh_value or not settings.xai_oauth_client_id:
        # Access token is expiring soon but we can't refresh
        # (missing refresh token or client id). Hand back the
        # access token anyway — better to send the request and let
        # the user see a 401 than to silently fall through to the
        # legacy key, which would mask the fact that they're using
        # OAuth at all.
        logger.warning(
            "XAI_OAUTH_REFRESH_SKIPPED workspace=%s reason=missing_refresh_or_client_id",
            workspace_root,
        )
        return access_token

    try:
        grant = await refresh_token(
            client_id=settings.xai_oauth_client_id,
            refresh_token_value=refresh_value,
        )
    except OAuthError as exc:
        logger.warning(
            "XAI_OAUTH_REFRESH_FAILED workspace=%s code=%s",
            workspace_root,
            exc.code,
        )
        # The refresh path 4xx'd — most likely the refresh token
        # is revoked. Return the stale access token; the next call
        # will 401 and the user will see the "re-login" notice
        # surfaced by the future chat-router error path.
        return access_token

    env[ACCESS_ENV_KEY] = grant.access_token
    if grant.refresh_token is not None:
        env[REFRESH_ENV_KEY] = grant.refresh_token
    expires_at = datetime.now(UTC) + timedelta(seconds=grant.expires_in)
    env[EXPIRES_AT_ENV_KEY] = expires_at.isoformat()
    save_workspace_env(workspace_root, env)
    return grant.access_token


def _needs_refresh(expires_at_raw: str) -> bool:
    """Return whether the stored access token is near or past expiry."""
    if not expires_at_raw:
        return False
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        logger.warning("XAI_OAUTH_BAD_EXPIRES_AT raw=%r", expires_at_raw)
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    cutoff = datetime.now(UTC) + timedelta(seconds=_REFRESH_LEAD_SECONDS)
    return expires_at <= cutoff
