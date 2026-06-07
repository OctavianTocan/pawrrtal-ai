"""Adapters for plugin-provided channel capabilities."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any, cast

from app.channels.base import Channel
from app.plugins.contributions import ChannelCapability
from app.plugins.errors import PluginError, PluginRuntimeError
from app.plugins.host import get_plugin_host

logger = logging.getLogger(__name__)

ChannelFactory = Callable[[ChannelCapability], Channel]


def build_channel_registry() -> dict[str, Channel]:
    """Build active channels from global and bundled plugin manifests."""
    try:
        _previous, snapshot = get_plugin_host().reload()
    except PluginError as exc:
        logger.warning("manifest plugin reload failed during channel composition: %s", exc)
        return {}

    channels: dict[str, Channel] = {}
    for outcome in snapshot.outcomes:
        manifest = outcome.manifest
        if not outcome.active or manifest is None:
            continue
        for capability in manifest.capabilities:
            if not isinstance(capability, ChannelCapability):
                continue
            if not outcome.state.is_capability_enabled(capability.id):
                continue
            channel = _build_channel(plugin_id=outcome.plugin_id, capability=capability)
            if channel is not None:
                channels[capability.surface] = channel
    return channels


def load_channel_factory(entrypoint: str) -> ChannelFactory:
    """Load a trusted Python channel factory from ``module:attribute``."""
    module_name, separator, attribute_path = entrypoint.partition(":")
    if not separator or not module_name or not attribute_path:
        raise PluginRuntimeError("channel entrypoint must use 'module:attribute' syntax")
    try:
        target: Any = importlib.import_module(module_name)
        for attribute in attribute_path.split("."):
            target = getattr(target, attribute)
    except (ImportError, AttributeError) as exc:
        raise PluginRuntimeError(f"could not load channel factory {entrypoint!r}") from exc
    if not callable(target):
        raise PluginRuntimeError(f"channel factory {entrypoint!r} is not callable")
    return cast(ChannelFactory, target)


def _build_channel(
    *,
    plugin_id: str,
    capability: ChannelCapability,
) -> Channel | None:
    """Build one channel adapter, logging and omitting malformed entries."""
    try:
        factory = load_channel_factory(capability.entrypoint)
        channel = factory(capability)
        _validate_channel(capability=capability, channel=channel)
        return channel
    except PluginRuntimeError as exc:
        logger.warning(
            "channel plugin load failed plugin_id=%s capability_id=%s error=%s",
            plugin_id,
            capability.id,
            exc,
        )
        return None


def _validate_channel(*, capability: ChannelCapability, channel: Channel) -> None:
    """Validate that a loaded object looks like a channel adapter."""
    if getattr(channel, "surface", None) != capability.surface:
        raise PluginRuntimeError(
            f"channel surface mismatch for {capability.id!r}: expected {capability.surface!r}"
        )
    if not callable(getattr(channel, "deliver", None)):
        raise PluginRuntimeError(f"channel {capability.id!r} has no callable deliver()")
