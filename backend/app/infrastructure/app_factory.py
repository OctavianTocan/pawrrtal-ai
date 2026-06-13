"""FastAPI app factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.plugins as _plugins
from app.infrastructure.lifecycle import default_registry
from app.infrastructure.logging.setup import configure_logging
from app.infrastructure.middleware.cors import with_cors
from app.infrastructure.middleware.logging import RequestLoggingMiddleware
from app.infrastructure.middleware.rate_limit import ChatRateLimitMiddleware
from app.infrastructure.router_registry import register_routers

# Import lifecycle modules for decorator side effects.
from app.infrastructure.shutdown import agy_api_client as _agy_api_client
from app.infrastructure.shutdown import provider_caches as _provider_caches
from app.infrastructure.shutdown import (
    provider_session_persist_drain as _provider_session_persist_drain,
)
from app.infrastructure.shutdown import tracing as _shutdown_tracing
from app.infrastructure.shutdown import turn_finalize_drain as _turn_finalize_drain
from app.infrastructure.startup import admin_seed as _admin_seed
from app.infrastructure.startup import database as _database
from app.infrastructure.startup import event_bus as _event_bus
from app.infrastructure.startup import plugin_lifespans as _plugin_lifespans
from app.infrastructure.startup import scheduler as _scheduler
from app.infrastructure.startup import stale_streaming_messages as _stale_streaming_messages
from app.infrastructure.startup import tracing as _startup_tracing
from app.infrastructure.startup import workspace_env_migration as _workspace_env_migration

configure_logging()

_LIFECYCLE_MODULES = (
    _startup_tracing,
    _database,
    _admin_seed,
    _workspace_env_migration,
    _stale_streaming_messages,
    _event_bus,
    _scheduler,
    _plugin_lifespans,
    _turn_finalize_drain,
    _provider_session_persist_drain,
    _provider_caches,
    _agy_api_client,
    _shutdown_tracing,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Run registered startup and shutdown hooks for the FastAPI application."""
    _ = (_LIFECYCLE_MODULES, _plugins)
    for hook in default_registry.startup_hooks():
        await hook.fn(app)
    try:
        yield
    finally:
        for hook in default_registry.shutdown_hooks():
            await hook.fn(app)


def create_app() -> FastAPI:
    """Create a FastAPI app instance with middleware and routes."""
    fastapi_app = FastAPI(
        lifespan=lifespan,
        title="Pawrrtal",
        description="An AI assistant platform",
        version="0.1.0",
    )
    fastapi_app.add_middleware(RequestLoggingMiddleware)
    fastapi_app.add_middleware(ChatRateLimitMiddleware)
    register_routers(fastapi_app)
    return fastapi_app


__all__ = ["create_app", "with_cors"]
