"""Tests for the Gemini one-off helpers (title-generation model fallback)."""

from __future__ import annotations

from app.conversations.gemini_utils import _first_gemini_slug
from app.providers.catalog import MODEL_CATALOG, first_catalog_model
from app.providers.model_id import Host


def test_first_gemini_slug_is_the_first_gemini_catalog_model() -> None:
    """The fallback resolves to the first google_ai entry's bare slug."""
    slug = _first_gemini_slug()
    gemini_entries = [entry for entry in MODEL_CATALOG if entry.host is Host.google_ai]
    assert gemini_entries, "catalog should expose at least one Gemini (google_ai) model"
    assert slug == gemini_entries[0].model
    # The Gemini SDK rejects host-prefixed canonical ids — must be a bare slug.
    assert ":" not in slug
    assert "/" not in slug


def test_first_gemini_slug_ignores_a_non_gemini_first_catalog_entry() -> None:
    """Regression guard: title generation goes through the Gemini SDK, so the
    fallback must be a Gemini model — not whatever the first *overall* catalog
    entry happens to be. The curated default was removed and the first catalog
    entry is now an Anthropic model, so handing its slug to Gemini would fail.
    """
    first = first_catalog_model()
    if first.host is not Host.google_ai:
        assert _first_gemini_slug() != first.model
