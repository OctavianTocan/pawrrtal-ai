"""Tests for the Paw Telegram verification scenario."""

from __future__ import annotations

from datetime import UTC

from app.cli.paw.verify.telegram import _parse_iso8601


def test_parse_iso8601_assumes_utc_for_naive_api_timestamp() -> None:
    """Naive API timestamps must still compare cleanly with UTC ``now``."""
    parsed = _parse_iso8601("2026-05-29T19:20:00")

    assert parsed is not None
    assert parsed.tzinfo is UTC
