"""Database URL normalization helpers for settings."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_database_url(database_url: str, sqlite_db_filename: str) -> str:
    """Return the configured database URL in a normalized form."""
    url = database_url.strip()
    if not url:
        filename = sqlite_db_filename.strip() or "pawrrtal.db"
        return f"sqlite:///./{filename}"

    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)

    parsed = urlparse(url)
    if parsed.scheme.startswith(("postgresql", "sqlite")):
        return url

    if not parsed.scheme:
        return f"sqlite:///{url}"

    return url


def sync_database_url(normalized_url: str) -> str:
    """Return the database URL formatted for synchronous connections."""
    if normalized_url.startswith("postgresql://"):
        return normalized_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if normalized_url.startswith("sqlite+aiosqlite://"):
        return normalized_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return normalized_url


def async_database_url(normalized_url: str) -> str:
    """Return the database URL formatted for asynchronous connections."""
    if normalized_url.startswith("postgresql://"):
        return normalized_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if normalized_url.startswith("sqlite://") and not normalized_url.startswith(
        "sqlite+aiosqlite://"
    ):
        return normalized_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return normalized_url
