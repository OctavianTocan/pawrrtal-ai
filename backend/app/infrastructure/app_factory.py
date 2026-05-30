"""FastAPI app factory for the current transitional backend layout."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.plugins as _plugins
from app.infrastructure.lifecycle import default_registry
from app.infrastructure.logging.setup import configure_logging
from app.infrastructure.middleware.backend_api_key import BackendApiKeyMiddleware
from app.infrastructure.middleware.cors import with_cors
from app.infrastructure.middleware.logging import RequestLoggingMiddleware
from app.infrastructure.middleware.rate_limit import ChatRateLimitMiddleware
from app.infrastructure.router_registry import register_routers

# Import lifecycle modules for decorator side effects.
from app.infrastructure.shutdown import codex_persist_drain as _codex_persist_drain
from app.infrastructure.shutdown import tracing as _shutdown_tracing
from app.infrastructure.startup import admin_seed as _admin_seed
from app.infrastructure.startup import database as _database
from app.infrastructure.startup import event_bus as _event_bus
from app.infrastructure.startup import gemini_cli_check as _gemini_cli_check
from app.infrastructure.startup import scheduler as _scheduler
from app.infrastructure.startup import telegram_lifespan as _telegram_lifespan
from app.infrastructure.startup import tracing as _startup_tracing
from app.infrastructure.startup import workspace_env_migration as _workspace_env_migration

configure_logging()

_LIFECYCLE_MODULES = (
    _startup_tracing,
    _gemini_cli_check,
    _database,
    _admin_seed,
    _workspace_env_migration,
    _event_bus,
    _scheduler,
    _telegram_lifespan,
    _codex_persist_drain,
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
    fastapi_app.add_middleware(BackendApiKeyMiddleware)
    register_routers(fastapi_app)
    return fastapi_app


__all__ = ["create_app", "with_cors"]
