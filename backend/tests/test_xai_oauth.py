"""Tests for the xAI OAuth device-code client (#372)."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.xai.oauth import (
    OAuthError,
    poll_for_token,
    refresh_token,
    request_device_code,
)

_RealAsyncClient = httpx.AsyncClient


@pytest.mark.anyio
async def test_request_device_code_returns_payload_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 200 response yields the parsed :class:`DeviceCodeRequest` shape."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "device_code": "DEV-xxx",
                "user_code": "ABCD-1234",
                "verification_uri": "https://x.ai/device",
                "expires_in": 600,
                "interval": 5,
            },
        )

    transport = httpx.MockTransport(_handler)
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_: _RealAsyncClient(transport=transport),
    )

    result = await request_device_code(client_id="pawrrtal-client")
    assert result.device_code == "DEV-xxx"
    assert result.user_code == "ABCD-1234"
    assert result.verification_uri == "https://x.ai/device"
    assert result.expires_in == 600
    assert result.interval == 5


@pytest.mark.anyio
async def test_request_device_code_raises_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An upstream error body surfaces as :class:`OAuthError`."""
    transport = httpx.MockTransport(lambda _: httpx.Response(500, text="upstream borked"))
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_: _RealAsyncClient(transport=transport),
    )
    with pytest.raises(OAuthError):
        await request_device_code(client_id="pawrrtal-client")


@pytest.mark.anyio
async def test_poll_for_token_returns_grant_on_first_authorised_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per RFC 8628 a 200 response is the terminal-success state."""

    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "ACC-xxx",
                "refresh_token": "REF-xxx",
                "expires_in": 3600,
                "scope": "chat:read chat:write stt:read",
            },
        )

    transport = httpx.MockTransport(_handler)
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_: _RealAsyncClient(transport=transport),
    )

    grant = await poll_for_token(
        client_id="pawrrtal-client",
        device_code="DEV-xxx",
        interval=1,
    )
    assert grant.access_token == "ACC-xxx"
    assert grant.refresh_token == "REF-xxx"
    assert grant.expires_in == 3600


@pytest.mark.anyio
async def test_poll_for_token_raises_on_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``access_denied`` is terminal — surface as ``OAuthError(code='access_denied')``."""
    transport = httpx.MockTransport(lambda _: httpx.Response(400, json={"error": "access_denied"}))
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_: _RealAsyncClient(transport=transport),
    )
    with pytest.raises(OAuthError) as exc_info:
        await poll_for_token(client_id="x", device_code="y", interval=1)
    assert exc_info.value.code == "access_denied"


@pytest.mark.anyio
async def test_poll_for_token_expires_when_deadline_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``authorization_pending`` forever → deadline kicks in with ``expired_token``.

    Hard cap on the deadline so the test runs in <0.5s — the prod
    deadline is 900s but we drop it to 1.5s here.
    """
    transport = httpx.MockTransport(
        lambda _: httpx.Response(400, json={"error": "authorization_pending"})
    )
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_: _RealAsyncClient(transport=transport),
    )
    with pytest.raises(OAuthError) as exc_info:
        await poll_for_token(
            client_id="x",
            device_code="y",
            interval=1,
            deadline_seconds=1.5,
        )
    assert exc_info.value.code == "expired_token"


@pytest.mark.anyio
async def test_refresh_token_returns_new_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful refresh returns the new grant; refresh-token preserved if absent."""

    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "NEW-ACC",
                "expires_in": 3600,
                # No ``refresh_token`` in response — caller keeps existing one.
            },
        )

    transport = httpx.MockTransport(_handler)
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_: _RealAsyncClient(transport=transport),
    )

    grant = await refresh_token(
        client_id="x",
        refresh_token_value="EXISTING-REFRESH",
    )
    assert grant.access_token == "NEW-ACC"
    assert grant.refresh_token == "EXISTING-REFRESH"  # preserved


@pytest.mark.anyio
async def test_refresh_token_raises_on_invalid_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expired / revoked refresh token surfaces as terminal failure."""
    transport = httpx.MockTransport(lambda _: httpx.Response(400, json={"error": "invalid_grant"}))
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_: _RealAsyncClient(transport=transport),
    )
    with pytest.raises(OAuthError) as exc_info:
        await refresh_token(client_id="x", refresh_token_value="EXPIRED")
    assert exc_info.value.code == "invalid_grant"
