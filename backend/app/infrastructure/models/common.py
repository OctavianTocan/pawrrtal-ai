"""Shared ORM model helpers."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp for SQLAlchemy defaults."""
    return datetime.now(UTC)
