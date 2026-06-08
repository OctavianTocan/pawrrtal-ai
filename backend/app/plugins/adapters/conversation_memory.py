"""Adapters for plugin-provided conversation memory backends."""

from __future__ import annotations

import importlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from app.plugins.contributions import ConversationMemoryCapability
from app.plugins.errors import PluginError, PluginRuntimeError
from app.plugins.host import get_plugin_host

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MemoryFactory = Callable[[], "ConversationMemoryBackend"]


class ConversationMemoryBackend(Protocol):
    """Runtime contract for one conversation memory backend."""

    async def load_history(
        self,
        session: AsyncSession,
        *,
        conversation_id: uuid.UUID,
        history_window: int,
    ) -> list[dict[str, str]] | None:
        """Return provider history, or ``None`` to use raw message history."""

    async def ingest_messages(
        self,
        session: AsyncSession,
        *,
        conversation_id: uuid.UUID,
        user_message_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> None:
        """Record the current turn's message rows for future retrieval."""

    def schedule_compaction(
        self,
        *,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        model_id: str,
    ) -> None:
        """Schedule any post-turn compaction work."""


@dataclass(frozen=True, slots=True)
class ConversationMemoryAdapter:
    """Loaded memory backend and manifest identity."""

    plugin_id: str
    capability_id: str
    backend: ConversationMemoryBackend


def resolve_conversation_memory(
    *,
    workspace_root: Path | None,
) -> ConversationMemoryAdapter | None:
    """Return the active conversation memory backend for a workspace."""
    try:
        _previous, snapshot = get_plugin_host().reload(workspace_root=workspace_root)
    except PluginError as exc:
        logger.warning("manifest plugin reload failed during memory composition: %s", exc)
        return None

    for plugin_id, capability in _memory_capabilities(snapshot.outcomes):
        adapter = _build_adapter(plugin_id=plugin_id, capability=capability)
        if adapter is not None:
            return adapter
    return None


def load_memory_factory(entrypoint: str) -> MemoryFactory:
    """Load a trusted Python memory backend factory from ``module:attribute``."""
    module_name, separator, attribute_path = entrypoint.partition(":")
    if not separator or not module_name or not attribute_path:
        raise PluginRuntimeError("conversation_memory entrypoint must use 'module:attribute'")
    try:
        target: Any = importlib.import_module(module_name)
        for attribute in attribute_path.split("."):
            target = getattr(target, attribute)
    except (ImportError, AttributeError) as exc:
        raise PluginRuntimeError(f"could not load memory factory {entrypoint!r}") from exc
    if not callable(target):
        raise PluginRuntimeError(f"conversation_memory factory {entrypoint!r} is not callable")
    return cast(MemoryFactory, target)


def _memory_capabilities(
    outcomes: tuple[Any, ...],
) -> tuple[tuple[str, ConversationMemoryCapability], ...]:
    capabilities = [
        (outcome.plugin_id, capability)
        for outcome in outcomes
        if outcome.active and outcome.manifest is not None
        for capability in outcome.manifest.capabilities
        if isinstance(capability, ConversationMemoryCapability)
        and outcome.state.is_capability_enabled(capability.id)
    ]
    return tuple(sorted(capabilities, key=lambda item: _sort_key(*item)))


def _sort_key(
    plugin_id: str,
    capability: ConversationMemoryCapability,
) -> tuple[int, int, str, str]:
    return (capability.order, -capability.priority, plugin_id, capability.id)


def _build_adapter(
    *,
    plugin_id: str,
    capability: ConversationMemoryCapability,
) -> ConversationMemoryAdapter | None:
    try:
        backend = load_memory_factory(capability.entrypoint)()
        _validate_backend(backend)
        return ConversationMemoryAdapter(
            plugin_id=plugin_id,
            capability_id=capability.id,
            backend=backend,
        )
    except PluginRuntimeError as exc:
        logger.warning(
            "conversation memory plugin load failed plugin_id=%s capability_id=%s error=%s",
            plugin_id,
            capability.id,
            exc,
        )
        return None


def _validate_backend(backend: object) -> None:
    for method_name in ("load_history", "ingest_messages", "schedule_compaction"):
        if not callable(getattr(backend, method_name, None)):
            raise PluginRuntimeError(f"conversation memory backend missing {method_name}()")
