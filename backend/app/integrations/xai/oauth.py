"""xAI OAuth 2.0 device-code client (#372).

Implements the three calls the Telegram + web composer surfaces
need: request a device code, poll the token endpoint, refresh an
expired access token. Each call is its own async function with a
narrow surface; the runtime that drives the polling state machine
lives in the bot / web composer (this module stays I/O-bounded +
framework-free).

Spec: RFC 8628 (https://datatracker.ietf.org/doc/html/rfc8628).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# Production xAI OAuth endpoints. Kept module-level so tests can
# monkeypatch the constants without poking the function bodies. The
# URLs themselves are placeholders that match xAI's documented
# device-code shape; the operator deployment can override via
# ``settings.xai_oauth_*`` once the upstream URL stabilises.
DEVICE_CODE_URL = "https://api.x.ai/oauth/device/code"
TOKEN_URL = "https://api.x.ai/oauth/token"
DEFAULT_SCOPE = "chat:read chat:write stt:read"

# Network defaults. Polling intervals come from the device-code
# response (RFC 8628 ``interval`` field); these caps protect against
# a misbehaving server.
_HTTP_TIMEOUT_SECONDS = 30.0
_MIN_POLL_INTERVAL_SECONDS = 1.0
_MAX_POLL_INTERVAL_SECONDS = 30.0
_MAX_POLL_DEADLINE_SECONDS = 900.0  # 15 min — xAI's documented device-code lifetime.
_SLOW_DOWN_INCREMENT_SECONDS = 5  # RFC 8628 S3.5: add 5s on ``slow_down``.


class OAuthError(RuntimeError):
    """Raised when xAI's OAuth endpoint returns a terminal failure.

    ``code`` carries the RFC 8628 error code (``access_denied`` /
    ``expired_token`` / ``slow_down`` / ``invalid_grant``). Use it
    to route the user-facing message ("you denied access on the
    device" vs "the device code expired before you authorised").
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DeviceCodeRequest:
    """One step of the device-code dance, as returned by xAI.

    ``device_code`` is the opaque payload we poll the token endpoint
    with. ``user_code`` + ``verification_uri`` are what we surface
    to the user. ``expires_in`` is the lifetime in seconds.
    ``interval`` is the polling cadence (server-set per RFC 8628).
    """

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class DeviceCodeGrant:
    """The token payload returned by a successful poll."""

    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str | None


async def request_device_code(
    *,
    client_id: str,
    scope: str = DEFAULT_SCOPE,
    url: str = DEVICE_CODE_URL,
) -> DeviceCodeRequest:
    """Open a device-code session and return the user-facing payload.

    Args:
        client_id: Pawrrtal's registered OAuth client id with xAI.
            Lives in ``settings.xai_oauth_client_id``; passed
            explicitly so callers can monkeypatch in tests.
        scope: Space-separated scope list. Defaults to the minimum
            xAI surface we need (chat + STT).
        url: Endpoint override for tests / staging.

    Raises:
        OAuthError: When xAI returns a non-200 status or the
            response body is missing required fields.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(
                url,
                data={"client_id": client_id, "scope": scope},
            )
        except httpx.RequestError as exc:
            logger.warning("XAI_OAUTH_DEVICE_CODE_REQUEST_FAIL error=%s", exc)
            raise OAuthError("xAI OAuth device endpoint unreachable.") from exc

    if response.status_code != 200:
        logger.warning(
            "XAI_OAUTH_DEVICE_CODE_HTTP_ERR status=%s body=%s",
            response.status_code,
            response.text[:200],
        )
        raise OAuthError(
            f"xAI OAuth device endpoint returned {response.status_code}.",
            code=str(response.status_code),
        )

    payload = response.json()
    try:
        return DeviceCodeRequest(
            device_code=str(payload["device_code"]),
            user_code=str(payload["user_code"]),
            verification_uri=str(payload["verification_uri"]),
            expires_in=int(payload.get("expires_in", _MAX_POLL_DEADLINE_SECONDS)),
            interval=_clamp_interval(payload.get("interval", 5)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "XAI_OAUTH_DEVICE_CODE_MALFORMED keys=%s",
            list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
        )
        raise OAuthError("xAI returned a malformed device-code payload.") from exc


async def poll_for_token(
    *,
    client_id: str,
    device_code: str,
    interval: int,
    deadline_seconds: float = _MAX_POLL_DEADLINE_SECONDS,
    url: str = TOKEN_URL,
) -> DeviceCodeGrant:
    """Poll the token endpoint until the user authorises (or the code expires).

    Returns the granted token + refresh token. ``deadline_seconds``
    bounds the wait so the worker can't loop forever on a
    misbehaving server. Per RFC 8628 the server may answer
    ``authorization_pending`` (keep polling) or ``slow_down``
    (increment the interval by 5s per RFC 8628 S3.5).
    """
    waited = 0.0
    current_interval = _clamp_interval(interval)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        while waited < deadline_seconds:
            try:
                response = await client.post(
                    url,
                    data={
                        "client_id": client_id,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                )
            except httpx.RequestError as exc:
                logger.warning("XAI_OAUTH_TOKEN_REQUEST_FAIL error=%s", exc)
                raise OAuthError("xAI OAuth token endpoint unreachable.") from exc

            if response.status_code == 200:
                payload = response.json()
                return DeviceCodeGrant(
                    access_token=str(payload["access_token"]),
                    refresh_token=payload.get("refresh_token"),
                    expires_in=int(payload.get("expires_in", 3600)),
                    scope=payload.get("scope"),
                )

            # Per RFC 8628 the pending / slow-down branches surface as
            # 400 + an ``error`` discriminator. Anything else is terminal.
            error_payload = _safe_json(response)
            code = error_payload.get("error") if isinstance(error_payload, dict) else None
            if code == "authorization_pending":
                await asyncio.sleep(current_interval)
                waited += current_interval
                continue
            if code == "slow_down":
                current_interval = _clamp_interval(current_interval + _SLOW_DOWN_INCREMENT_SECONDS)
                await asyncio.sleep(current_interval)
                waited += current_interval
                continue
            if code in ("access_denied", "expired_token", "invalid_grant"):
                raise OAuthError(f"xAI OAuth grant failed: {code}.", code=code)
            # Unknown error -- log + bail so we don't loop on a permanent
            # failure that doesn't match the RFC's error vocabulary.
            logger.warning(
                "XAI_OAUTH_TOKEN_UNKNOWN_ERR status=%s code=%s body=%s",
                response.status_code,
                code,
                response.text[:200],
            )
            raise OAuthError(
                f"xAI OAuth token endpoint returned unexpected status "
                f"{response.status_code} (code={code!r}).",
                code=code,
            )

    raise OAuthError("xAI device code expired before authorisation.", code="expired_token")


async def refresh_token(
    *,
    client_id: str,
    refresh_token_value: str,
    url: str = TOKEN_URL,
) -> DeviceCodeGrant:
    """Trade a refresh token for a fresh access token.

    Same response shape as :func:`poll_for_token`. xAI returns a
    new refresh token when one is granted; otherwise the field is
    absent and the caller keeps the existing one.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(
                url,
                data={
                    "client_id": client_id,
                    "refresh_token": refresh_token_value,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.RequestError as exc:
            logger.warning("XAI_OAUTH_REFRESH_FAIL error=%s", exc)
            raise OAuthError("xAI OAuth refresh endpoint unreachable.") from exc

    if response.status_code != 200:
        error_payload = _safe_json(response)
        code = error_payload.get("error") if isinstance(error_payload, dict) else None
        logger.warning(
            "XAI_OAUTH_REFRESH_HTTP_ERR status=%s code=%s",
            response.status_code,
            code,
        )
        raise OAuthError(
            f"xAI OAuth refresh returned {response.status_code} (code={code!r}).",
            code=code,
        )

    payload = response.json()
    return DeviceCodeGrant(
        access_token=str(payload["access_token"]),
        refresh_token=payload.get("refresh_token") or refresh_token_value,
        expires_in=int(payload.get("expires_in", 3600)),
        scope=payload.get("scope"),
    )


def _clamp_interval(value: object) -> int:
    """Coerce + clamp the poll-interval value to the safe range."""
    try:
        interval = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        interval = int(_MIN_POLL_INTERVAL_SECONDS)
    return max(int(_MIN_POLL_INTERVAL_SECONDS), min(int(_MAX_POLL_INTERVAL_SECONDS), interval))


def _safe_json(response: httpx.Response) -> object:
    """``response.json()`` that returns an empty dict on parse failure."""
    try:
        return response.json()
    except ValueError:
        return {}
