"""Tests for :func:`app.channels.telegram.model_defaults.resolve_effective_model_id`.

The resolver owns the two-step fallback chain that every Telegram
surface walks: conversation override → first catalog entry. Centralising
it means every regression here is caught once.
"""

from __future__ import annotations

from app.channels.telegram.model_defaults import resolve_effective_model_id
from app.providers.catalog import MODEL_CATALOG, first_catalog_model


def test_resolve_returns_conversation_override_when_set() -> None:
    """A set conversation override is returned verbatim."""
    pinned = MODEL_CATALOG[1].id
    assert resolve_effective_model_id(conversation_model_id=pinned) == pinned


def test_resolve_falls_back_to_first_catalog_model_when_no_override() -> None:
    """No conversation override → first catalog entry."""
    assert resolve_effective_model_id(conversation_model_id=None) == first_catalog_model().id
