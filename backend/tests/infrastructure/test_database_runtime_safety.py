"""Database runtime safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from app.infrastructure.database.safety import classify_database_target
from app.infrastructure.startup import database as startup_database


def test_classify_database_target_marks_dev_sqlite_repo_local_safe(tmp_path: Path) -> None:
    """Local dev may use the implicit repo-local SQLite fallback."""
    report = classify_database_target(
        database_url="",
        sqlite_db_filename="pawrrtal.db",
        env="dev",
        repo_root=tmp_path,
        cwd=tmp_path,
    )

    assert report.safe is True
    assert report.classification == "sqlite-repo-local"


def test_classify_database_target_rejects_staging_sqlite(tmp_path: Path) -> None:
    """Staging/prod must not boot against SQLite."""
    report = classify_database_target(
        database_url="sqlite:///./pawrrtal.db",
        sqlite_db_filename="pawrrtal.db",
        env="staging",
        repo_root=tmp_path,
        cwd=tmp_path,
    )

    assert report.safe is False
    assert report.classification == "sqlite-repo-local"
    assert (
        report.hint
        == "Set DATABASE_URL to a Postgres service URL before starting this environment."
    )


def test_classify_database_target_redacts_postgres_password(tmp_path: Path) -> None:
    """Preflight output must not leak DB credentials."""
    report = classify_database_target(
        database_url="postgres://user:pw@db.example.com:5432/app",
        sqlite_db_filename="pawrrtal.db",
        env="prod",
        repo_root=tmp_path,
        cwd=tmp_path,
    )

    assert report.safe is True
    assert report.classification == "postgres"
    assert report.redacted_target == "postgresql://user:***@db.example.com:5432/app"


@pytest.mark.anyio
async def test_start_database_rejects_prod_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FastAPI startup fails before table creation when prod points at SQLite."""
    from app.infrastructure.config import settings

    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "database_url", "sqlite:///./pawrrtal.db")
    monkeypatch.setattr(settings, "sqlite_db_filename", "pawrrtal.db")

    async def fail_create_db_and_tables() -> None:
        raise AssertionError("startup should fail before touching the DB")

    monkeypatch.setattr(
        startup_database,
        "create_db_and_tables",
        fail_create_db_and_tables,
    )

    with pytest.raises(RuntimeError, match="Unsafe database target"):
        await startup_database.start_database(FastAPI())
