"""FastAPI application entry point.

Defines all API routes, configures middleware, and wires up authentication.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.api.appearance import get_appearance_router
from app.api.audit import get_audit_router
from app.api.auth import get_auth_router

# TODO(pawrrtal-1irw): re-add `from app.api.channels import get_channels_router`
#   here once Phase 4 ships, then re-include below in create_app.
from app.api.chat import get_chat_router
from app.api.conversations import get_conversations_router
from app.api.cost import get_cost_router
from app.api.exports import get_exports_router
from app.api.health import get_health_router
from app.api.models import get_models_router
from app.api.oauth import get_oauth_router
from app.api.personalization import get_personalization_router
from app.api.projects import get_projects_router
from app.api.scheduled_jobs import get_scheduled_jobs_router
from app.api.stt import get_stt_router
from app.api.workspace import get_workspace_router
from app.api.workspace_env import get_workspace_env_router
from app.cli.admin_seed import seed_admin_user
from app.core.config import settings
from app.core.event_bus import AgentHandler, EventBus, NotificationService
from app.core.event_bus.global_bus import set_event_bus
from app.core.middleware import BackendApiKeyMiddleware
from app.core.rate_limit import ChatRateLimitMiddleware
from app.core.request_logging import RequestLoggingMiddleware
from app.core.scheduler import JobScheduler
from app.core.telemetry import setup_tracing, shutdown_tracing
from app.db import create_db_and_tables

# TODO(pawrrtal-obsd): re-add `from app.integrations.telegram import telegram_lifespan`
#   once Phase 11 rebuilds the bot service, then wrap the rest of the
#   lifespan in `async with telegram_lifespan() as telegram_service:`.
from app.integrations.webhooks import get_webhooks_router
from app.logger_setup import (
    configure_logging,  # Set up logging configuration (this should be done before any loggers are used)
)
from app.schemas import (
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.users import auth_backend, fastapi_users

# Configure logging at the very start of the application. This ensures that all loggers in the app will use this configuration.
configure_logging()

# --- Lifespan ----------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Run startup tasks (database table creation) before the app begins serving."""
    # OpenTelemetry tracing bootstrap.  No-op when OTEL_EXPORTER_OTLP_ENDPOINT
    # is unset, so dev environments are unaffected.  Must run before any
    # outbound httpx call so the autoinstrumenter wraps the global client.
    setup_tracing(app)
    await create_db_and_tables()
    # This creates the admin user on every startup, but the UserManager will check if it already exists and skip creation if so, so it's idempotent and safe to run every time.
    await seed_admin_user()
    # PR 10: spin up the event bus before any request can fire so the
    # consumer task is ready when the chat router or Telegram dispatcher
    # publishes the first ``TurnStartedEvent``.  Stashed on
    # ``app.state`` for handlers that want to publish from inside a route.
    event_bus = EventBus()
    await event_bus.start()
    app.state.event_bus = event_bus
    set_event_bus(event_bus)
    # PR 12: spin up the cron scheduler after the bus so re-hydrated
    # jobs that fire on startup have a publisher to land on.  No-op
    # when ``SCHEDULER_ENABLED=false``.
    scheduler: JobScheduler | None = None
    if settings.scheduler_enabled:
        scheduler = JobScheduler()
        await scheduler.start()
        app.state.scheduler = scheduler
    else:
        app.state.scheduler = None
    # TODO(pawrrtal-obsd): wrap the rest of this lifespan in
    #   `async with telegram_lifespan() as telegram_service:` once Phase 11
    #   ships. Stash the live service on `app.state.telegram_service` so
    #   the webhook route can hand updates to aiogram, and pass
    #   `telegram_bot=telegram_service.bot` to NotificationService below.
    app.state.telegram_service = None
    # Register agent + notification subscribers. While Telegram is stripped
    # the notification service runs with `telegram_bot=None`; it logs and
    # skips delivery when no bot is configured (see handlers.py).
    agent_handler = AgentHandler()
    agent_handler.register(event_bus)
    notification_service = NotificationService(telegram_bot=None)
    notification_service.register(event_bus)
    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()
        set_event_bus(None)
        await event_bus.stop()
        shutdown_tracing()


# --- App & Middleware --------------------------------------------------------


def create_app() -> FastAPI:
    """Create a FastAPI app instance with middleware and routes."""
    fastapi_app = FastAPI(
        lifespan=lifespan,
        title="Pawrrtal",
        description="An AI assistant platform",
        version="0.1.0",
    )
    # Request-logging middleware must be added before any route is registered
    # so it wraps every endpoint. Each request gets a unique ID logged on
    # entry and exit (see app/core/request_logging.py).
    fastapi_app.add_middleware(RequestLoggingMiddleware)
    # ChatRateLimitMiddleware is a no-op when chat_rate_limit_per_minute=0
    # (the default), so registering it unconditionally costs nothing in
    # dev but is wired up for prod just by flipping the env var.
    fastapi_app.add_middleware(ChatRateLimitMiddleware)
    # Added last so Starlette wraps it outermost: invalid deployment API keys
    # are rejected before route/auth work. Disabled when BACKEND_API_KEY is unset.
    fastapi_app.add_middleware(BackendApiKeyMiddleware)
    fastapi_app.include_router(
        fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
    )
    fastapi_app.include_router(
        get_auth_router(),
    )
    fastapi_app.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        prefix="/auth",
        tags=["auth"],
    )
    fastapi_app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate),
        prefix="/users",
        tags=["users"],
    )

    # Custom API routes for conversations and chat.
    fastapi_app.include_router(
        get_conversations_router(),
    )
    fastapi_app.include_router(
        get_chat_router(),
    )
    fastapi_app.include_router(
        get_models_router(),
    )
    fastapi_app.include_router(
        get_stt_router(),
    )
    fastapi_app.include_router(
        get_projects_router(),
    )
    fastapi_app.include_router(
        get_personalization_router(),
    )
    fastapi_app.include_router(
        get_appearance_router(),
    )
    fastapi_app.include_router(
        get_oauth_router(),
    )
    # TODO(pawrrtal-1irw): include `get_channels_router()` here once
    #   Phase 4 ships the /api/v1/channels routes. Don't forget the
    #   import at the top of this file.
    fastapi_app.include_router(
        get_workspace_router(),
    )
    fastapi_app.include_router(
        get_workspace_env_router(),
    )
    fastapi_app.include_router(
        get_audit_router(),
    )
    fastapi_app.include_router(
        get_cost_router(),
    )
    fastapi_app.include_router(
        get_exports_router(),
    )
    fastapi_app.include_router(
        get_webhooks_router(),
    )
    fastapi_app.include_router(
        get_scheduled_jobs_router(),
    )
    fastapi_app.include_router(
        get_health_router(),
    )

    return fastapi_app


def with_cors(asgi_app: ASGIApp) -> ASGIApp:
    """Wrap the whole ASGI app so even unhandled errors include CORS headers."""
    return CORSMiddleware(
        asgi_app,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Create the app instance.
app = with_cors(create_app())
