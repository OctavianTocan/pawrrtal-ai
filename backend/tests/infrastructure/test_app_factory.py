"""Tests for FastAPI app construction and router registration."""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.infrastructure.app_factory import create_app
from app.infrastructure.middleware.backend_api_key import BackendApiKeyMiddleware
from app.infrastructure.middleware.logging import RequestLoggingMiddleware
from app.infrastructure.middleware.rate_limit import ChatRateLimitMiddleware
from app.infrastructure.router_registry import register_routers


def test_create_app_returns_fastapi_instance() -> None:
    """The factory returns the bare FastAPI app used by tests and CORS wrapping."""
    app = create_app()
    assert isinstance(app, FastAPI)


def test_create_app_registers_expected_middleware() -> None:
    """The factory wires the operational middleware from the old main module."""
    app = create_app()
    middleware_classes = {cast(type[object], middleware.cls) for middleware in app.user_middleware}
    expected_classes: set[type[object]] = {
        BackendApiKeyMiddleware,
        ChatRateLimitMiddleware,
        RequestLoggingMiddleware,
    }
    assert middleware_classes == expected_classes


def test_register_routers_adds_health_endpoint() -> None:
    """Router registration exposes the canonical public health endpoint."""
    app = FastAPI()
    register_routers(app)
    assert any(getattr(route, "path", None) == "/api/v1/health" for route in app.routes)


@pytest.mark.anyio
async def test_create_app_health_endpoint_responds() -> None:
    """Factory-created app can serve a health request without lifespan startup."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/api/v1/health", "/api/v1/health/ready", "/health"])
async def test_health_endpoints_bypass_backend_api_key(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    """Health probes remain reachable when the backend transport key is enabled."""
    from app.infrastructure.config import settings

    monkeypatch.setattr(settings, "backend_api_key", "required-key")
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(path)

    assert response.status_code != 401


@pytest.mark.anyio
async def test_telegram_webhook_bypasses_backend_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Telegram webhook auth relies on Telegram's secret header, not X-Pawrrtal-Key."""
    from app.infrastructure.config import settings

    monkeypatch.setattr(settings, "backend_api_key", "required-key")
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/channels/telegram/webhook", json={})

    assert response.status_code != 401
