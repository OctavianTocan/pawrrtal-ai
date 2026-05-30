"""Central router registration for the current transitional app layout."""

from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from fastapi import APIRouter, FastAPI

_ROUTER_FACTORIES: tuple[tuple[str, str], ...] = (
    ("app.infrastructure.auth.dev_login", "get_auth_router"),
    ("app.conversations.router", "get_conversations_router"),
    ("app.chat.router", "get_chat_router"),
    ("app.chat.completions.router", "get_completions_router"),
    ("app.chat.catalog.router", "get_models_router"),
    ("app.projects.router", "get_projects_router"),
    ("app.workspace.personalization.router", "get_personalization_router"),
    ("app.workspace.appearance.router", "get_appearance_router"),
    ("app.infrastructure.auth.oauth.router", "get_oauth_router"),
    ("app.channels.router", "get_channels_router"),
    ("app.workspace.router", "get_workspace_router"),
    ("app.workspace.env.router", "get_workspace_env_router"),
    ("app.governance.audit.router", "get_audit_router"),
    ("app.governance.cost.router", "get_cost_router"),
    ("app.conversations.exports.router", "get_exports_router"),
    ("app.agents.scheduling.jobs_router", "get_scheduled_jobs_router"),
    ("app.agents.scheduling.heartbeat_router", "get_heartbeat_router"),
    ("app.integrations.mcp_servers.router", "get_mcp_servers_router"),
    ("app.infrastructure.observability.health.router", "get_health_router"),
    ("app.infrastructure.observability.lcm.router", "get_lcm_router"),
)


def _import_attr(module_path: str, attr_name: str) -> Any:
    """Import ``attr_name`` from ``module_path``."""
    module = import_module(module_path)
    return getattr(module, attr_name)


def _router_from_factory(module_path: str, factory_name: str) -> APIRouter:
    """Load a router factory and return its router."""
    factory = cast("Any", _import_attr(module_path, factory_name))
    return cast("APIRouter", factory())


def _include_fastapi_users_routers(app: FastAPI) -> None:
    """Register fastapi-users routers with their established prefixes."""
    users = import_module("app.infrastructure.auth.users")
    schemas = import_module("app.schemas")

    fastapi_users = users.fastapi_users
    auth_backend = users.auth_backend
    user_create = schemas.UserCreate
    user_read = schemas.UserRead
    user_update = schemas.UserUpdate

    app.include_router(
        fastapi_users.get_auth_router(backend=auth_backend),
        prefix="/auth/jwt",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_register_router(user_read, user_create),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_users_router(user_read, user_update),
        prefix="/api/v1/users",
        tags=["users"],
    )
    app.include_router(
        fastapi_users.get_users_router(user_read, user_update),
        prefix="/users",
        tags=["users-compat"],
    )


def register_routers(app: FastAPI) -> None:
    """Register every router on the FastAPI application."""
    _include_fastapi_users_routers(app)

    for module_path, factory_name in _ROUTER_FACTORIES:
        app.include_router(_router_from_factory(module_path, factory_name))
