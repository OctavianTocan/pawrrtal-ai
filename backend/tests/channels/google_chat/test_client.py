"""Google Chat REST client safety behavior."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.channels.google_chat import client as client_module

pytestmark = pytest.mark.anyio


class _FakePostClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def post(self, *_args: Any, **_kwargs: Any) -> httpx.Response:
        return self.response


class _FakeStream:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> httpx.Response:
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FakeStreamClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    def stream(self, *_args: Any, **_kwargs: Any) -> _FakeStream:
        return _FakeStream(self.response)


async def test_acknowledge_returns_false_on_api_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_headers() -> dict[str, str]:
        return {"Authorization": "Bearer test"}

    monkeypatch.setattr(client_module, "_headers", _fake_headers)
    monkeypatch.setattr(client_module, "_client", lambda: _FakePostClient(httpx.Response(500)))

    ok = await client_module.acknowledge(
        project_id="p",
        subscription_id="s",
        ack_ids=["ack-1"],
    )

    assert ok is False


async def test_download_attachment_rejects_declared_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_headers() -> dict[str, str]:
        return {"Authorization": "Bearer test"}

    response = httpx.Response(200, headers={"content-length": "10"}, content=b"")
    monkeypatch.setattr(client_module, "_headers", _fake_headers)
    monkeypatch.setattr(client_module, "_client", lambda: _FakeStreamClient(response))

    data = await client_module.download_attachment(resource_name="r", max_bytes=3)

    assert data is None


async def test_read_limited_response_rejects_chunked_oversize() -> None:
    response = httpx.Response(200, content=b"abcdef")

    data = await client_module._read_limited_response(response, max_bytes=3)

    assert data is None
