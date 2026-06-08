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


class _FailingPatchClient:
    async def patch(self, *_args: Any, **_kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("temporary network failure")


def _failing_patch_client() -> _FailingPatchClient:
    return _FailingPatchClient()


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


class _FakeGetClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def get(self, *_args: Any, **_kwargs: Any) -> httpx.Response:
        return self.response


async def test_acknowledge_returns_false_on_api_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_headers() -> dict[str, str]:
        return {"Authorization": "Bearer test"}

    monkeypatch.setattr(client_module, "_headers", _fake_headers)
    monkeypatch.setattr(client_module, "_client", lambda: _FakePostClient(httpx.Response(500)))

    await client_module.acknowledge(
        project_id="p",
        subscription_id="s",
        ack_ids=["ack-1"],
    )


async def test_update_message_returns_false_on_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_headers() -> dict[str, str]:
        return {"Authorization": "Bearer test"}

    monkeypatch.setattr(client_module, "_headers", _fake_headers)
    monkeypatch.setattr(client_module, "_client", _failing_patch_client)

    ok = await client_module.update_message(message_name="spaces/A/messages/M", text="done")

    assert ok is False


async def test_download_attachment_rejects_declared_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_headers() -> dict[str, str]:
        return {"Authorization": "Bearer test"}

    response = httpx.Response(200, headers={"content-length": "10"}, content=b"")
    monkeypatch.setattr(client_module, "_headers", _fake_headers)
    monkeypatch.setattr(client_module, "_client", lambda: _FakeGetClient(response))

    data = await client_module.download_attachment(resource_name="r", max_bytes=3)

    assert data is None


async def test_download_attachment_rejects_response_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_headers() -> dict[str, str]:
        return {"Authorization": "Bearer test"}

    response = httpx.Response(200, content=b"abcdef")
    monkeypatch.setattr(client_module, "_headers", _fake_headers)
    monkeypatch.setattr(client_module, "_client", lambda: _FakeGetClient(response))

    data = await client_module.download_attachment(resource_name="r", max_bytes=3)

    assert data is None
