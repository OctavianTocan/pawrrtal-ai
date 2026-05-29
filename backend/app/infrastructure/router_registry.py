"""Central router registration for the current transitional app layout."""

from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from fastapi import APIRouter, FastAPI

_ROUTER_FACTORIES: tuple[tuple[str, str], ...] = (
    ("app.api.auth", "get_auth_router"),
    ("app.api.conversations", "get_conversations_router"),
    ("app.api.chat", "get_chat_router"),
    ("app.api.completions", "get_completions_router"),
    ("app.api.models", "get_models_router"),
    ("app.api.projects", "get_projects_router"),
    ("app.api.personalization", "get_personalization_router"),
    ("app.api.appearance", "get_appearance_router"),
    ("app.api.oauth", "get_oauth_router"),
    ("app.api.channels", "get_channels_router"),
    ("app.api.workspace", "get_workspace_router"),
    ("app.api.workspace_env", "get_workspace_env_router"),
    ("app.api.audit", "get_audit_router"),
    ("app.api.cost", "get_cost_router"),
    ("app.api.exports", "get_exports_router"),
    ("app.api.scheduled_jobs", "get_scheduled_jobs_router"),
    ("app.api.heartbeat", "get_heartbeat_router"),
    ("app.api.mcp_servers", "get_mcp_servers_router"),
    ("app.api.health", "get_health_router"),
    ("app.api.lcm", "get_lcm_router"),
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
