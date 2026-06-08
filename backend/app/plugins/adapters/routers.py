"""Adapters for plugin-provided API router capabilities."""

from __future__ import annotations

import logging
from typing import cast

from fastapi import APIRouter

from app.plugins.contributions import RouterCapability
from app.plugins.entrypoints import load_entrypoint_callable
from app.plugins.errors import PluginError, PluginRuntimeError
from app.plugins.host import get_plugin_host

logger = logging.getLogger(__name__)


def build_plugin_routers() -> list[APIRouter]:
    """Build active API routers from bundled plugin manifests."""
    try:
        _previous, snapshot = get_plugin_host().reload()
    except PluginError as exc:
        logger.warning("manifest plugin reload failed during router composition: %s", exc)
        return []

    routers: list[APIRouter] = []
    for outcome in snapshot.outcomes:
        manifest = outcome.manifest
        if not outcome.active or manifest is None:
            continue
        for capability in manifest.capabilities:
            if not isinstance(capability, RouterCapability):
                continue
            if not outcome.state.is_capability_enabled(capability.id):
                continue
            router = _build_router(plugin_id=outcome.plugin_id, capability=capability)
            if router is not None:
                routers.append(router)
    return routers


def _build_router(*, plugin_id: str, capability: RouterCapability) -> APIRouter | None:
    """Build one plugin-declared API router."""
    try:
        factory = cast(
            "object",
            load_entrypoint_callable(capability.entrypoint, context="router factory"),
        )
        if not callable(factory):
            raise PluginRuntimeError(f"router factory {capability.entrypoint!r} is not callable")
        router = factory()
        _validate_router(capability=capability, router=router)
        return cast(APIRouter, router)
    except PluginRuntimeError as exc:
        logger.warning(
            "router plugin load failed plugin_id=%s capability_id=%s error=%s",
            plugin_id,
            capability.id,
            exc,
        )
        return None


def _validate_router(*, capability: RouterCapability, router: object) -> None:
    """Validate that a loaded object is an APIRouter with the declared prefix."""
    if not isinstance(router, APIRouter):
        raise PluginRuntimeError(f"router {capability.id!r} did not return an APIRouter")
    if router.prefix != capability.prefix:
        raise PluginRuntimeError(
            f"router prefix mismatch for {capability.id!r}: expected {capability.prefix!r}"
        )
