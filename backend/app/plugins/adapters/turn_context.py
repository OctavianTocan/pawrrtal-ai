"""Adapters for plugin-provided turn context providers."""

from __future__ import annotations

import importlib
import logging
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from app.plugins.contributions import TurnContextProviderCapability
from app.plugins.errors import PluginError, PluginRuntimeError
from app.plugins.host import get_plugin_host

logger = logging.getLogger(__name__)

TurnContextProvider = Callable[["TurnContextProviderContext"], Coroutine[Any, Any, str | None]]
DraftUpdater = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class TurnContextProviderContext:
    """Context passed to plugin providers before the main model turn."""

    conversation_id: uuid.UUID
    user_id: uuid.UUID
    question: str
    workspace_root: Path
    draft_updater: DraftUpdater | None = None


@dataclass(frozen=True)
class TurnContextProviderAdapter:
    """Loaded runtime adapter for one manifest-declared context provider."""

    plugin_id: str
    capability_id: str
    title: str | None
    order: int
    timeout_seconds: float | None
    provider: TurnContextProvider

    @property
    def log_name(self) -> str:
        """Return a stable name for logs and diagnostics."""
        provider_name = getattr(self.provider, "__name__", self.provider.__class__.__name__)
        return f"{self.plugin_id}/{self.capability_id}:{provider_name}"


def build_turn_context_providers(*, workspace_root: Path) -> list[TurnContextProviderAdapter]:
    """Build active turn context providers for one workspace snapshot."""
    try:
        _previous, snapshot = get_plugin_host().reload(workspace_root=workspace_root)
    except PluginError as exc:
        logger.warning("manifest plugin reload failed during turn context composition: %s", exc)
        return []

    adapters: list[TurnContextProviderAdapter] = []
    for outcome in snapshot.outcomes:
        manifest = outcome.manifest
        if not outcome.active or manifest is None:
            continue
        for capability in manifest.capabilities:
            if not isinstance(capability, TurnContextProviderCapability):
                continue
            if not outcome.state.is_capability_enabled(capability.id):
                continue
            adapter = _build_adapter(
                plugin_id=outcome.plugin_id,
                capability=capability,
            )
            if adapter is not None:
                adapters.append(adapter)

    return sorted(
        adapters,
        key=lambda adapter: (adapter.order, adapter.plugin_id, adapter.capability_id),
    )


def load_turn_context_provider(entrypoint: str) -> TurnContextProvider:
    """Load a trusted Python turn context provider from ``module:attribute``."""
    module_name, separator, attribute_path = entrypoint.partition(":")
    if not separator or not module_name or not attribute_path:
        raise PluginRuntimeError(
            "turn_context_provider entrypoint must use 'module:attribute' syntax"
        )

    try:
        target: Any = importlib.import_module(module_name)
        for attribute in attribute_path.split("."):
            target = getattr(target, attribute)
    except (ImportError, AttributeError) as exc:
        raise PluginRuntimeError(f"could not load turn context provider {entrypoint!r}") from exc

    if not callable(target):
        raise PluginRuntimeError(f"turn context provider {entrypoint!r} is not callable")
    return cast(TurnContextProvider, target)


def _build_adapter(
    *,
    plugin_id: str,
    capability: TurnContextProviderCapability,
) -> TurnContextProviderAdapter | None:
    """Build one adapter, logging and omitting malformed runtime entries."""
    try:
        provider = load_turn_context_provider(capability.entrypoint)
    except PluginRuntimeError as exc:
        logger.warning(
            "turn context provider load failed plugin_id=%s capability_id=%s error=%s",
            plugin_id,
            capability.id,
            exc,
        )
        return None
    return TurnContextProviderAdapter(
        plugin_id=plugin_id,
        capability_id=capability.id,
        title=capability.title,
        order=capability.order,
        timeout_seconds=_timeout_seconds(capability.budget),
        provider=provider,
    )


def _timeout_seconds(budget: dict[str, Any]) -> float | None:
    """Return an optional per-provider timeout from the manifest budget."""
    raw = budget.get("timeout_seconds")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float) and raw > 0:
        return float(raw)
    return None
