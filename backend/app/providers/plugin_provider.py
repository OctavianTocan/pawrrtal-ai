"""Runtime support for manifest-backed provider plugins."""

from __future__ import annotations

import importlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from app.plugins.contributions import ProviderCapability, ProviderModel
from app.plugins.errors import PluginError, PluginRuntimeError
from app.plugins.host import get_plugin_host
from app.providers.base import AILLM, ReasoningEffort
from app.providers.model_id import InvalidModelId, UnknownModelId

logger = logging.getLogger(__name__)

_PLUGIN_MODEL_ID_RE = re.compile(
    r"^(?P<host>[a-z][a-z0-9_]{1,62}):"
    r"(?P<vendor>[a-z][a-z0-9_-]*)/"
    r"(?P<model>[a-z0-9][a-z0-9.\-_]*)$"
)

ProviderFactory = Callable[["ProviderFactoryContext"], AILLM]


@dataclass(frozen=True, slots=True)
class PluginParsedModelId:
    """Structurally parsed provider-plugin model id."""

    host: str
    vendor: str
    model: str
    raw: str

    @property
    def id(self) -> str:
        """Return the canonical plugin model id."""
        return f"{self.host}:{self.vendor}/{self.model}"


@dataclass(frozen=True, slots=True)
class PluginModelEntry:
    """One model declared by an active provider plugin."""

    plugin_id: str
    capability_id: str
    entrypoint: str
    parsed: PluginParsedModelId
    display_name: str
    short_name: str
    description: str
    sort_order: int
    supports_reasoning: tuple[ReasoningEffort, ...]
    supports_images: bool
    supports_tools: bool
    capability: ProviderCapability
    model: ProviderModel

    @property
    def id(self) -> str:
        """Return the canonical model id."""
        return self.parsed.id


@dataclass(frozen=True, slots=True)
class ProviderFactoryContext:
    """Context passed to trusted provider plugin factories."""

    plugin_id: str
    capability_id: str
    model_id: PluginParsedModelId
    workspace_root: Path | None
    capability: ProviderCapability
    model: ProviderModel


def parse_plugin_model_id(raw: str) -> PluginParsedModelId:
    """Parse a dynamic provider-plugin model id."""
    match = _PLUGIN_MODEL_ID_RE.match(raw)
    if match is None:
        raise InvalidModelId(f"not a valid plugin model ID: {raw!r}")
    return PluginParsedModelId(
        host=match.group("host"),
        vendor=match.group("vendor"),
        model=match.group("model"),
        raw=raw,
    )


def provider_model_entries(*, workspace_root: Path | None) -> tuple[PluginModelEntry, ...]:
    """Return active provider-plugin model entries for a workspace."""
    try:
        _previous, snapshot = get_plugin_host().reload(workspace_root=workspace_root)
    except PluginError as exc:
        logger.warning("manifest plugin reload failed during provider model composition: %s", exc)
        return ()

    entries: list[PluginModelEntry] = []
    for outcome in snapshot.outcomes:
        manifest = outcome.manifest
        if not outcome.active or manifest is None:
            continue
        for capability in manifest.capabilities:
            if not isinstance(capability, ProviderCapability):
                continue
            if not outcome.state.is_capability_enabled(capability.id):
                continue
            entries.extend(_entries_for_capability(outcome.plugin_id, capability))
    return tuple(sorted(entries, key=lambda entry: (entry.sort_order, entry.id)))


def find_provider_model(
    model_id: str,
    *,
    workspace_root: Path | None,
) -> PluginModelEntry | None:
    """Return the active provider-plugin model matching ``model_id``."""
    parsed = parse_plugin_model_id(model_id)
    for entry in provider_model_entries(workspace_root=workspace_root):
        if entry.parsed == parsed:
            return entry
    return None


def resolve_plugin_llm(
    model_id: str,
    *,
    workspace_root: Path | None,
) -> AILLM:
    """Resolve a manifest-backed provider plugin for ``model_id``."""
    entry = find_provider_model(model_id, workspace_root=workspace_root)
    if entry is None:
        parsed = parse_plugin_model_id(model_id)
        raise UnknownModelId(f"plugin model not active: {parsed.id}")
    factory = load_provider_factory(entry.entrypoint)
    return factory(
        ProviderFactoryContext(
            plugin_id=entry.plugin_id,
            capability_id=entry.capability_id,
            model_id=entry.parsed,
            workspace_root=workspace_root,
            capability=entry.capability,
            model=entry.model,
        )
    )


def load_provider_factory(entrypoint: str) -> ProviderFactory:
    """Load a trusted Python provider factory from ``module:attribute``."""
    module_name, separator, attribute_path = entrypoint.partition(":")
    if not separator or not module_name or not attribute_path:
        raise PluginRuntimeError("provider entrypoint must use 'module:attribute' syntax")
    try:
        target: Any = importlib.import_module(module_name)
        for attribute in attribute_path.split("."):
            target = getattr(target, attribute)
    except (ImportError, AttributeError) as exc:
        raise PluginRuntimeError(f"could not load provider factory {entrypoint!r}") from exc
    if not callable(target):
        raise PluginRuntimeError(f"provider factory {entrypoint!r} is not callable")
    return cast(ProviderFactory, target)


def _entries_for_capability(
    plugin_id: str,
    capability: ProviderCapability,
) -> list[PluginModelEntry]:
    """Return model entries for one provider capability."""
    entries: list[PluginModelEntry] = []
    for model in capability.models:
        parsed = _parse_declared_model_id(plugin_id=plugin_id, model_id=model.id)
        if parsed is None:
            continue
        entries.append(
            PluginModelEntry(
                plugin_id=plugin_id,
                capability_id=capability.id,
                entrypoint=capability.entrypoint,
                parsed=parsed,
                display_name=model.name,
                short_name=model.name,
                description=capability.description,
                sort_order=model.sort_order,
                supports_reasoning=_reasoning(model.reasoning),
                supports_images=model.supports_images,
                supports_tools=model.supports_tools,
                capability=capability,
                model=model,
            )
        )
    return entries


def _parse_declared_model_id(*, plugin_id: str, model_id: str) -> PluginParsedModelId | None:
    """Parse one model id declared under a provider plugin."""
    raw = model_id if ":" in model_id else f"{plugin_id}:{model_id}"
    try:
        parsed = parse_plugin_model_id(raw)
    except InvalidModelId as exc:
        logger.warning("provider plugin model id skipped plugin_id=%s error=%s", plugin_id, exc)
        return None
    if parsed.host != plugin_id:
        logger.warning(
            "provider plugin model id skipped plugin_id=%s model_id=%s reason=host_mismatch",
            plugin_id,
            raw,
        )
        return None
    return parsed


def _reasoning(values: tuple[str, ...]) -> tuple[ReasoningEffort, ...]:
    """Return declared reasoning values constrained to Pawrrtal levels."""
    allowed: set[ReasoningEffort] = {"minimal", "low", "medium", "high", "extra-high"}
    return tuple(value for value in values if value in allowed)
