"""FastAPI application entry point.

Defines all API routes, configures middleware, and wires up authentication.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

import app.plugins
from app.api.appearance import get_appearance_router
from app.api.audit import get_audit_router
from app.api.auth import get_auth_router
from app.api.channels import get_channels_router
from app.api.chat import get_chat_router
from app.api.completions import get_completions_router
from app.api.conversations import get_conversations_router
from app.api.cost import get_cost_router
from app.api.exports import get_exports_router
from app.api.health import get_health_router
from app.api.heartbeat import get_heartbeat_router
from app.api.lcm import get_lcm_router
from app.api.mcp_servers import get_mcp_servers_router
from app.api.models import get_models_router
from app.api.oauth import get_oauth_router
from app.api.personalization import get_personalization_router
from app.api.projects import get_projects_router
from app.api.scheduled_jobs import get_scheduled_jobs_router
from app.api.stt import get_stt_router
from app.api.workspace import get_workspace_router
from app.api.workspace_env import get_workspace_env_router
from app.cli.admin_seed import seed_admin_user
from app.cli.migrate_workspace_env import migrate_user_keyed_env_files_for_all_users
from app.core.config import settings
from app.core.event_bus import AgentHandler, EventBus, NotificationService
from app.core.event_bus.global_bus import set_event_bus
from app.core.middleware import BackendApiKeyMiddleware
from app.core.providers.gemini_cli import (
    GEMINI_BINARY_NAME,
    is_gemini_cli_available,
)
from app.core.rate_limit import ChatRateLimitMiddleware
from app.core.request_logging import RequestLoggingMiddleware
from app.core.scheduler import JobScheduler, set_active_scheduler
from app.core.telemetry import setup_tracing, shutdown_tracing
from app.db import create_db_and_tables
from app.integrations.telegram import telegram_lifespan
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


def _log_gemini_cli_status() -> None:
    """Emit a one-line log line describing Gemini CLI availability.

    Called once during :func:`lifespan` so operators see a clear signal
    when the ``gemini`` binary is missing from PATH. The Gemini CLI
    provider (``host=Host.gemini_cli`` models) needs the binary to
    function; the rest of Pawrrtal does not, so we never block startup.

    Delegates the actual probe to :func:`is_gemini_cli_available` so the
    binary-name constant lives in exactly one place.
    """
    import logging  # noqa: PLC0415 — keep startup imports lazy
    import shutil  # noqa: PLC0415

    log = logging.getLogger(__name__)
    if not is_gemini_cli_available():
        log.warning(
            "GEMINI_CLI_UNAVAILABLE binary=%s path=$PATH "
            "(install with `npm install -g @google/gemini-cli` to enable "
            "gemini-cli:* models; other providers unaffected)",
            GEMINI_BINARY_NAME,
        )
        return
    log.info("GEMINI_CLI_FOUND path=%s", shutil.which(GEMINI_BINARY_NAME))


# --- Lifespan ----------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Run startup tasks (database table creation) before the app begins serving."""
    # OpenTelemetry tracing bootstrap.  No-op when OTEL_EXPORTER_OTLP_ENDPOINT
    # is unset, so dev environments are unaffected.  Must run before any
    # outbound httpx call so the autoinstrumenter wraps the global client.
    setup_tracing(app)
    # Surface Gemini CLI availability once at startup so an operator
    # sees a single clear log line instead of an opaque per-request
    # "subprocess spawn failed" error. We never refuse to boot — the
    # rest of the providers stay usable when the CLI is absent.
    _log_gemini_cli_status()
    await create_db_and_tables()
    # This creates the admin user on every startup, but the UserManager will check if it already exists and skip creation if so, so it's idempotent and safe to run every time.
    await seed_admin_user()
    # One-time migration of legacy user-keyed `.env` files to the new
    # workspace-keyed layout.  Idempotent — when the source file is missing
    # or the destination already exists, the helper returns without writing.
    # See ADR 2026-05-15-plugin-system-and-notion-integration.mdx.
    await migrate_user_keyed_env_files_for_all_users()
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
        set_active_scheduler(scheduler)
    else:
        app.state.scheduler = None
        set_active_scheduler(None)
    # Bring the Telegram channel up alongside the HTTP server when a bot
    # token is configured. The context manager yields None and is a no-op
    # when the channel is disabled, so this stays safe for stripped-down
    # deployments (CI, ephemeral previews, ...). Stash the service on
    # `app.state` so the webhook route can hand updates to aiogram.
    async with telegram_lifespan() as telegram_service:
        app.state.telegram_service = telegram_service
        # Follow-on: register the agent + notification subscribers AFTER the
        # Telegram service is up so the notification service has a live
        # bot instance.  Both are no-ops when the relevant pieces are
        # disabled (no bot → notifications skip; no default user → agent
        # handler logs + skips).
        agent_handler = AgentHandler()
        agent_handler.register(event_bus)
        notification_service = NotificationService(
            telegram_bot=telegram_service.bot if telegram_service is not None else None
        )
        notification_service.register(event_bus)
        try:
            yield
        finally:
            if scheduler is not None:
                await scheduler.stop()
            set_active_scheduler(None)
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
        fastapi_users.get_auth_router(backend=auth_backend), prefix="/auth/jwt", tags=["auth"]
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
        get_completions_router(),
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
    fastapi_app.include_router(
        get_channels_router(),
    )
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
        get_heartbeat_router(),
    )
    fastapi_app.include_router(
        get_mcp_servers_router(),
    )
    fastapi_app.include_router(
        get_health_router(),
    )
    fastapi_app.include_router(
        get_lcm_router(),
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
app = with_cors(create_app())  # type: ignore[assignment]
