"""Tests for :mod:`app.providers.catalog`."""

from __future__ import annotations

import pytest

from app.providers.catalog import (
    CATALOG_ETAG,
    MODEL_CATALOG,
    find,
    first_catalog_model,
    is_known,
    require_known,
)
from app.providers.model_id import (
    InvalidModelId,
    UnknownModelId,
    parse_model_id,
)


def test_catalog_not_empty() -> None:
    assert len(MODEL_CATALOG) > 0


def test_every_entry_id_round_trips_through_parser() -> None:
    for entry in MODEL_CATALOG:
        parsed = parse_model_id(entry.id)
        assert parsed.host is entry.host
        assert parsed.vendor is entry.vendor
        assert parsed.model == entry.model
        assert parsed.id == entry.id


def test_find_returns_entry_for_known_id() -> None:
    target = first_catalog_model()
    parsed = parse_model_id(target.id)
    assert find(parsed) is target


def test_find_returns_none_for_unknown_model() -> None:
    parsed = parse_model_id("google/gemini-9999-future-preview")
    assert find(parsed) is None


def test_is_known_matches_find() -> None:
    target = first_catalog_model()
    parsed = parse_model_id(target.id)
    assert is_known(parsed) is True
    unknown = parse_model_id("google/gemini-9999-future-preview")
    assert is_known(unknown) is False


def test_require_known_returns_entry() -> None:
    target = first_catalog_model()
    assert require_known(target.id) is target


def test_require_known_raises_invalid_for_bad_format() -> None:
    with pytest.raises(InvalidModelId):
        require_known("not a model id")


def test_require_known_raises_unknown_for_well_formed_miss() -> None:
    with pytest.raises(UnknownModelId):
        require_known("google/gemini-9999-future-preview")


def test_etag_is_stable() -> None:
    assert isinstance(CATALOG_ETAG, str)
    assert len(CATALOG_ETAG) == 16
    # Importing twice yields the same hash (module-level computation).
    from app.providers.catalog import CATALOG_ETAG as ETAG_AGAIN

    assert ETAG_AGAIN == CATALOG_ETAG


# ---------------------------------------------------------------------------
# Issue #352 layer L5 — explicit must-have asserts.
#
# Snapshots invite rubber-stamp updates. Explicit "model X must be in the
# catalog" asserts make the contract visible at review time: a PR that
# drops one of these models fails CI with a clear message instead of a
# silent diff. Each ID below is the canonical ``host:vendor/model`` wire
# form (the same string the chat router persists on conversations).
# ---------------------------------------------------------------------------

_MUST_HAVE_MODEL_IDS: tuple[str, ...] = (
    # Anthropic Claude — frontier + balanced + fast tiers.
    "agent-sdk:anthropic/claude-opus-4-7",
    "agent-sdk:anthropic/claude-sonnet-4-6",
    "agent-sdk:anthropic/claude-haiku-4-5",
    # Google Gemini — Pro + Flash + Flash Lite preview pipeline.
    "google-ai:google/gemini-3-flash-preview",
    "google-ai:google/gemini-3.5-flash",
    "google-ai:google/gemini-3.1-pro-preview",
    "google-ai:google/gemini-3.1-flash-lite",
    # xAI — the single Grok 4.3 SKU; if this drops, the picker has
    # nothing behind the xAI host.
    "xai:xai/grok-4.3",
    # OpenCode Go — the original two entries that the #349 sweep
    # expanded on. These two are the load-bearing ones referenced in
    # screenshots / docs / status output.
    "opencode-go:zai/glm-5.1",
    "opencode-go:moonshot/kimi-k2.6",
)


def test_catalog_contains_every_must_have_model_id() -> None:
    """Pin every load-bearing model so a future PR can't drop one silently (#352 L5).

    Explicit asserts > snapshot tests: a PR that drops one of these
    models fails CI with the canonical wire id printed in the failure
    output, rather than a silent diff that a reviewer might rubber-stamp.
    Adding a new model is a one-line diff here too — the asymmetry is
    the point.
    """
    catalog_ids = {entry.id for entry in MODEL_CATALOG}
    missing = [mid for mid in _MUST_HAVE_MODEL_IDS if mid not in catalog_ids]
    assert not missing, f"Catalog dropped must-have ids: {missing}"


def test_every_catalog_entry_has_non_empty_display_metadata() -> None:
    """A smoke check that no entry slipped in with empty display strings.

    The picker concatenates ``display_name`` / ``short_name`` /
    ``description`` into Telegram inline keyboard labels. Empty strings
    would render as a blank row and the user couldn't tell which model
    they were picking.
    """
    for entry in MODEL_CATALOG:
        assert entry.display_name.strip(), f"{entry.id} has empty display_name"
        assert entry.short_name.strip(), f"{entry.id} has empty short_name"
        assert entry.description.strip(), f"{entry.id} has empty description"
