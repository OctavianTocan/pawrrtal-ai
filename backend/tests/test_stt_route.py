"""Tests for the speech-to-text proxy route (``api/stt.py``).

The route used to call ``resolve_api_key("XAI_API_KEY")`` directly,
falling through to ``settings.xai_api_key`` only when no workspace
override was set. After #372 it funnels every credential lookup
through :func:`resolve_xai_credentials` so the OAuth access token
(refreshed transparently when near expiry) is preferred over the
legacy long-lived API key.

These tests pin the new contract: the route surfaces 503 when the
helper resolves to ``None``, and forwards the resolved bearer token
verbatim into the upstream ``Authorization`` header.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_stt_route_503s_when_no_xai_credential_resolves(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: object,
) -> None:
    """When ``resolve_xai_credentials`` returns ``None`` the route surfaces 503.

    Pins the swap (#372 follow-up): the legacy code had a two-step
    "workspace key OR gateway key" fallback inline. The new code
    delegates that to the helper, so a single ``None`` reply must
    short-circuit the upstream call and the user sees the "not
    configured" notice instead of a guaranteed 401 from xAI.
    """
    monkeypatch.setattr(
        "app.api.stt.resolve_xai_credentials",
        _async_return(None),
    )
    # Force the xAI path by disabling the alt-backend dispatch.
    monkeypatch.setattr("app.integrations.voice.resolve_transcriber", lambda: None)

    response = await client.post(
        "/api/v1/stt",
        files={"file": ("voice.webm", b"\x00\x01\x02", "audio/webm")},
    )
    assert response.status_code == 503
    assert "Speech-to-text is not configured" in response.json()["detail"]


@pytest.mark.anyio
async def test_stt_route_forwards_resolved_credential_to_xai(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: object,
) -> None:
    """The route forwards whatever ``resolve_xai_credentials`` returns.

    This is the OAuth path's success case: the helper returns an
    access token, and the route MUST put it in the
    ``Authorization: Bearer <token>`` header without re-deriving it
    from the legacy ``XAI_API_KEY`` setting. We mock the upstream
    httpx call so we can inspect what header was sent.
    """
    seen_headers: dict[str, str] = {}

    def _upstream(request: httpx.Request) -> httpx.Response:
        seen_headers.update({k.lower(): v for k, v in request.headers.items()})
        return httpx.Response(200, json={"text": "hello world", "duration": 1.2, "words": []})

    transport = httpx.MockTransport(_upstream)
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **_: httpx.AsyncClient(transport=transport),
    )
    monkeypatch.setattr(
        "app.api.stt.resolve_xai_credentials",
        _async_return("oauth-access-token-xyz"),
    )
    monkeypatch.setattr("app.integrations.voice.resolve_transcriber", lambda: None)

    response = await client.post(
        "/api/v1/stt",
        files={"file": ("voice.webm", b"\x00\x01\x02", "audio/webm")},
    )
    assert response.status_code == 200
    assert response.json()["text"] == "hello world"
    assert seen_headers.get("authorization") == "Bearer oauth-access-token-xyz"


def _async_return(value: object) -> Callable[..., Awaitable[object]]:
    """Return an async callable that ignores its args and returns ``value``."""

    async def _stub(*_args: object, **_kwargs: object) -> object:
        return value

    return _stub
