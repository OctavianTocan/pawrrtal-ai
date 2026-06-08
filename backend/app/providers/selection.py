"""Provider selection helpers shared by turn preparation surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.providers.base import AILLM
from app.providers.catalog import ModelEntry, find, first_catalog_model, require_known
from app.providers.factory import resolve_llm
from app.providers.model_id import InvalidModelId, UnknownModelId, parse_model_id


@dataclass(frozen=True)
class ProviderSelection:
    """Resolved provider plus the model ID the turn should record."""

    provider: AILLM
    effective_model_id: str
    warning: str | None = None
    bad_model_id: str | None = None


def default_model_id() -> str:
    """Return the catalog default model ID."""
    return first_catalog_model().id


def effective_model_id(*, conversation_model_id: str | None) -> str:
    """Resolve conversation override to catalog default."""
    return conversation_model_id or default_model_id()


def model_entry_or_default(model_id: str) -> ModelEntry:
    """Return the catalog entry for ``model_id`` or the default entry."""
    try:
        parsed = parse_model_id(model_id)
    except InvalidModelId:
        return first_catalog_model()
    return find(parsed) or first_catalog_model()


def model_display(model_id: str | None, *, default_suffix: bool = False) -> str:
    """Render a model ID with an optional default marker."""
    if model_id:
        return model_id
    suffix = " (default)" if default_suffix else ""
    return f"{default_model_id()}{suffix}"


def require_provider(
    model_id: str,
    *,
    workspace_root: Path | None = None,
) -> ProviderSelection:
    """Resolve ``model_id`` and propagate catalog/parse failures."""
    require_known(model_id)
    return ProviderSelection(
        provider=resolve_llm(model_id, workspace_root=workspace_root),
        effective_model_id=model_id,
    )


def provider_or_default(
    model_id: str,
    *,
    workspace_root: Path | None = None,
) -> ProviderSelection:
    """Resolve ``model_id``, falling back to the catalog default on bad IDs."""
    try:
        return require_provider(model_id, workspace_root=workspace_root)
    except (InvalidModelId, UnknownModelId) as exc:
        fallback_id = default_model_id()
        return ProviderSelection(
            provider=resolve_llm(fallback_id, workspace_root=workspace_root),
            effective_model_id=fallback_id,
            warning=str(exc),
            bad_model_id=model_id,
        )
