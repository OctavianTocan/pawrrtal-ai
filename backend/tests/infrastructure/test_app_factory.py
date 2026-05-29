"""Tests for FastAPI app construction and router registration."""

from __future__ import annotations

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
    middleware_classes = {middleware.cls for middleware in app.user_middleware}
    assert middleware_classes == {
        BackendApiKeyMiddleware,
        ChatRateLimitMiddleware,
        RequestLoggingMiddleware,
    }


def test_register_routers_adds_health_endpoint() -> None:
    """Router registration exposes the canonical public health endpoint."""
    app = FastAPI()
    register_routers(app)
    assert any(route.path == "/api/v1/health" for route in app.routes)


@pytest.mark.anyio
async def test_create_app_health_endpoint_responds() -> None:
    """Factory-created app can serve a health request without lifespan startup."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
