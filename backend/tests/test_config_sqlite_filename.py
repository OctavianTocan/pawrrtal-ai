"""Tests for the implicit-SQLite filename fallback in ``Settings``.

Closes #279: ``SQLITE_DB_FILENAME`` lets parallel checkouts and one-off
experiments point the implicit SQLite default at a different ``.db`` file
without spelling out a full ``sqlite:///...`` URL. An explicit
``DATABASE_URL`` always wins.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.infrastructure.config import Settings  # noqa: E402 — sys.path tweak above must precede

_REQUIRED_DEFAULTS: dict[str, str] = {
    "AUTH_SECRET": "x",
    "GOOGLE_API_KEY": "x",
    "WORKSPACE_ENCRYPTION_KEY": "x",
    "CORS_ORIGINS": "[]",
}


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip env-var / .env interference so the test owns ``Settings`` inputs.

    The repo's ``backend/.env`` (or operator-set env vars) typically
    carries a ``DATABASE_URL`` pointing at a real Postgres instance.
    Without this fixture, ``Settings()`` would silently inherit that
    URL and the test would assert against the host's config instead
    of the canonical SQLite fallback path we care about.
    """
    for key in (
        "DATABASE_URL",
        "SQLITE_DB_FILENAME",
        "AUTH_SECRET",
        "GOOGLE_API_KEY",
        "WORKSPACE_ENCRYPTION_KEY",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in _REQUIRED_DEFAULTS.items():
        monkeypatch.setenv(key, value)


def test_default_sqlite_filename_is_pawrrtal_db(isolated_env: None) -> None:
    """No env var → implicit fallback writes to ``./pawrrtal.db``."""
    settings = Settings(_env_file=None)
    assert settings._normalized_database_url == "sqlite:///./pawrrtal.db"


def test_sqlite_db_filename_overrides_default(isolated_env: None) -> None:
    """``SQLITE_DB_FILENAME`` rewrites the implicit fallback filename."""
    settings = Settings(_env_file=None, sqlite_db_filename="experiment.db")
    assert settings._normalized_database_url == "sqlite:///./experiment.db"


def test_database_url_wins_over_sqlite_filename(isolated_env: None) -> None:
    """An explicit ``DATABASE_URL`` is never overridden by the filename setting."""
    settings = Settings(
        _env_file=None,
        database_url="postgresql://u:p@h:5432/d",
        sqlite_db_filename="ignored.db",
    )
    assert settings._normalized_database_url == "postgresql://u:p@h:5432/d"


def test_empty_sqlite_filename_falls_back_to_default(isolated_env: None) -> None:
    """A blank ``SQLITE_DB_FILENAME`` falls back to the canonical default."""
    settings = Settings(_env_file=None, sqlite_db_filename="   ")
    assert settings._normalized_database_url == "sqlite:///./pawrrtal.db"
