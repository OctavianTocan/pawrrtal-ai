"""Single source of truth for which models pawrrtal supports.

Catalog entries carry the canonical ``host:vendor/model`` identity
plus display metadata. Composes the per-host tuples into the public
:data:`MODEL_CATALOG` and exposes the lookup helpers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from app.providers.model_id import ParsedModelId, UnknownModelId, parse_model_id

from .agy_cli import AGY_CLI_ENTRIES
from .entries import (
    ANTHROPIC_ENTRIES,
    GOOGLE_ENTRIES,
    XAI_ENTRIES,
    ModelEntry,
)
from .gemini_cli import GEMINI_CLI_ENTRIES
from .openai import OPENAI_ENTRIES
from .opencode_go import OPENCODE_GO_ENTRIES

__all__ = [
    "CATALOG_ETAG",
    "MODEL_CATALOG",
    "ModelEntry",
    "default_model",
    "find",
    "is_known",
    "require_known",
]


MODEL_CATALOG: tuple[ModelEntry, ...] = (
    *ANTHROPIC_ENTRIES,
    *GOOGLE_ENTRIES,
    *GEMINI_CLI_ENTRIES,
    *AGY_CLI_ENTRIES,
    *XAI_ENTRIES,
    *OPENAI_ENTRIES,
    *OPENCODE_GO_ENTRIES,
)


# Module-import-time invariant: exactly one default.
# Explicit raise (not ``assert``) so ``python -O`` cannot strip it.
_default_count = sum(1 for e in MODEL_CATALOG if e.is_default)
if _default_count != 1:
    raise ValueError(f"MODEL_CATALOG must have exactly one default; found {_default_count}")


def _hash_catalog(catalog: tuple[ModelEntry, ...]) -> str:
    """Stable hash of the catalog used as the HTTP ``ETag`` value."""
    payload = json.dumps(
        [asdict(e) for e in catalog],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


CATALOG_ETAG: str = _hash_catalog(MODEL_CATALOG)
"""Catalog hash, computed once at import. Exposed via the ``ETag``
response header so clients can revalidate cheaply with
`If-None-Match`."""


def default_model() -> ModelEntry:
    """Return the entry marked ``is_default=True``.

    Returns:
        The single default entry. The module-import-time invariant
        guarantees exactly one exists.
    """
    return next(e for e in MODEL_CATALOG if e.is_default)


def find(parsed: ParsedModelId) -> ModelEntry | None:
    """Look up a catalog entry by parsed identifier.

    Args:
        parsed: Pre-parsed identifier (callers go through
            :func:`parse_model_id` first).

    Returns:
        The matching :class:`ModelEntry` or ``None``.
    """
    for entry in MODEL_CATALOG:
        if (
            entry.host is parsed.host
            and entry.vendor is parsed.vendor
            and entry.model == parsed.model
        ):
            return entry
    return None


def is_known(parsed: ParsedModelId) -> bool:
    """Return whether ``parsed`` is in :data:`MODEL_CATALOG`."""
    return find(parsed) is not None


def require_known(model_id: str) -> ModelEntry:
    """Parse ``model_id`` and look it up; raise on either failure.

    Args:
        model_id: Wire-form model identifier (any of the accepted
            input shapes — see :func:`parse_model_id`).

    Returns:
        The catalog entry.

    Raises:
        InvalidModelId: If the string fails to parse.
        UnknownModelId: If the string parses but isn't in the
            catalog.
    """
    parsed = parse_model_id(model_id)
    entry = find(parsed)
    if entry is None:
        raise UnknownModelId(f"model not in catalog: {parsed.id}")
    return entry
