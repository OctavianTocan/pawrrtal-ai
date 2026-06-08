"""Startup hook for plugin-declared process lifespans."""

from __future__ import annotations

import importlib
import inspect
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from app.infrastructure.lifecycle import shutdown_hook, startup_hook
from app.plugins.contributions import ChannelCapability
from app.plugins.errors import PluginError, PluginRuntimeError
from app.plugins.host import get_plugin_host
from app.plugins.registry import ContributionRegistrySnapshot, PluginLoadOutcome

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

_STATE_KEY = "plugin_lifespan_contexts"


@dataclass(frozen=True, slots=True)
class PluginLifespanContext:
    """One entered plugin lifespan context."""

    plugin_id: str
    capability_id: str
    context_manager: Any


@startup_hook(order=70)
async def start_plugin_lifespans(app: FastAPI) -> None:
    """Enter active plugin lifespans."""
    await reload_plugin_lifespans(app)


@shutdown_hook(order=40)
async def stop_plugin_lifespans(app: FastAPI) -> None:
    """Exit active plugin lifespans."""
    await _stop_plugin_lifespans(app)


async def reload_plugin_lifespans(app: FastAPI) -> None:
    """Reload plugin manifests and restart plugin lifespans."""
    await _stop_plugin_lifespans(app)
    snapshot = _reload_plugins()
    if snapshot is None:
        setattr(app.state, _STATE_KEY, ())
        return
    contexts = [
        context
        for context in [
            await _enter_lifespan(app, plugin_id=plugin_id, capability=capability)
            for plugin_id, capability in _channel_lifespans(snapshot)
        ]
        if context is not None
    ]
    setattr(app.state, _STATE_KEY, tuple(contexts))


def _reload_plugins() -> ContributionRegistrySnapshot | None:
    try:
        _previous, snapshot = get_plugin_host().reload()
        return snapshot
    except PluginError as exc:
        logger.warning("plugin reload failed during lifecycle startup: %s", exc)
        return None


def _channel_lifespans(
    snapshot: ContributionRegistrySnapshot,
) -> tuple[tuple[str, ChannelCapability], ...]:
    capabilities = [
        (outcome.plugin_id, capability)
        for outcome in snapshot.outcomes
        for capability in _outcome_channel_lifespans(outcome)
    ]
    return tuple(sorted(capabilities, key=lambda item: _lifespan_order(item[1])))


def _outcome_channel_lifespans(
    outcome: PluginLoadOutcome,
) -> tuple[ChannelCapability, ...]:
    manifest = outcome.manifest
    if not outcome.active or manifest is None:
        return ()
    return tuple(
        capability
        for capability in manifest.capabilities
        if isinstance(capability, ChannelCapability)
        and capability.lifespan
        and outcome.state.is_capability_enabled(capability.id)
    )


def _lifespan_order(capability: ChannelCapability) -> int:
    raw_order = capability.lifespan.get("order", 100)
    try:
        return int(raw_order) if isinstance(raw_order, int | str) else 100
    except ValueError:
        return 100


async def _enter_lifespan(
    app: FastAPI,
    *,
    plugin_id: str,
    capability: ChannelCapability,
) -> PluginLifespanContext | None:
    try:
        context_manager = _load_callable(_required_lifespan_value(capability, "entrypoint"))()
        service = await context_manager.__aenter__()
        _store_lifespan_state(app, capability=capability, context_manager=context_manager)
        _store_service_state(app, capability=capability, service=service)
        await _run_post_start(app, capability=capability, service=service)
        return PluginLifespanContext(
            plugin_id=plugin_id,
            capability_id=capability.id,
            context_manager=context_manager,
        )
    except Exception:
        logger.exception(
            "PLUGIN_LIFESPAN_START_FAILED plugin_id=%s capability_id=%s",
            plugin_id,
            capability.id,
        )
        return None


def _required_lifespan_value(capability: ChannelCapability, key: str) -> str:
    value = capability.lifespan.get(key)
    if isinstance(value, str) and value:
        return value
    raise PluginRuntimeError(f"channel {capability.id!r} lifespan.{key} must be a string")


def _optional_lifespan_value(capability: ChannelCapability, key: str) -> str | None:
    value = capability.lifespan.get(key)
    return value if isinstance(value, str) and value else None


def _store_lifespan_state(
    app: FastAPI,
    *,
    capability: ChannelCapability,
    context_manager: Any,
) -> None:
    key = _optional_lifespan_value(capability, "context_key")
    if key:
        setattr(app.state, key, context_manager)


def _store_service_state(
    app: FastAPI,
    *,
    capability: ChannelCapability,
    service: Any,
) -> None:
    key = _optional_lifespan_value(capability, "service_key")
    if key:
        setattr(app.state, key, service)


async def _run_post_start(
    app: FastAPI,
    *,
    capability: ChannelCapability,
    service: Any,
) -> None:
    entrypoint = _optional_lifespan_value(capability, "post_start")
    if entrypoint is None:
        return
    result = _load_callable(entrypoint)(app, service)
    if inspect.isawaitable(result):
        await result


async def _stop_plugin_lifespans(app: FastAPI) -> None:
    contexts = tuple(getattr(app.state, _STATE_KEY, ()))
    setattr(app.state, _STATE_KEY, ())
    for context in reversed(contexts):
        try:
            await context.context_manager.__aexit__(None, None, None)
        except Exception:
            logger.exception(
                "PLUGIN_LIFESPAN_STOP_FAILED plugin_id=%s capability_id=%s",
                context.plugin_id,
                context.capability_id,
            )


def _load_callable(entrypoint: str) -> Any:
    module_name, separator, attribute_path = entrypoint.partition(":")
    if not separator or not module_name or not attribute_path:
        raise PluginRuntimeError("plugin lifespan entrypoint must use 'module:attribute' syntax")
    try:
        target = importlib.import_module(module_name)
        for attribute in attribute_path.split("."):
            target = getattr(target, attribute)
    except (ImportError, AttributeError) as exc:
        raise PluginRuntimeError(f"could not load plugin lifespan {entrypoint!r}") from exc
    if not callable(target):
        raise PluginRuntimeError(f"plugin lifespan {entrypoint!r} is not callable")
    return cast(Any, target)
