"""Regression test for the Alembic advisory-lock DDL-rollback bug on Postgres.

Closes the silent-migration-failure bug in ``alembic/env.py``:
``run_migrations_online()`` acquired a session advisory lock with
``connection.execute(text("SELECT pg_advisory_lock(...)"))`` *before*
``context.begin_transaction()``. Under SQLAlchemy 2.0 that ``execute``
auto-begins a transaction Alembic does not own; when the
``with connectable.connect()`` block closes the connection, that
transaction — carrying every migration's DDL — is rolled back. The net
effect on a *fresh* Postgres database: ``alembic upgrade head`` prints a
full upgrade run and exits 0, but creates **zero** tables. The fix commits
that auto-begun transaction immediately after taking the lock (the lock is
session-scoped, so committing does not release it) so Alembic's own
transaction can own and COMMIT the schema.

This test runs the *real* ``alembic upgrade head`` (as a subprocess, exactly
as production/Railway does) against a throwaway Postgres database and asserts
that the schema actually landed. It fails against the unfixed ``env.py``
(0 tables, no ``alembic_version``) and passes against the fix.

**Postgres-only.** SQLite never enters the advisory-lock branch, so the bug
cannot reproduce there. When no Postgres is reachable (e.g. CI without a PG
service) the test skips cleanly rather than failing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

import pytest

# psycopg (v3) is the project's Postgres driver. If it is not installed the
# whole test is meaningless — skip at collection time. The static import below
# (under TYPE_CHECKING only) gives mypy the ``Connection`` type without making
# the dependency mandatory at runtime.
psycopg = pytest.importorskip("psycopg")

if TYPE_CHECKING:
    from psycopg import Connection

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# The base ("admin") Postgres URL used both to create/drop the throwaway DB and
# as the connection target for the actual upgrade. Operators / CI can override
# via ``ALEMBIC_TEST_POSTGRES_URL``; the default matches the repo's local dev
# container documented in CLAUDE.md (localhost:5432, user/pw/db ``pawrrtal``).
_DEFAULT_PG_URL = "postgresql://pawrrtal:pawrrtal_dev@localhost:5432/pawrrtal"
_BASE_PG_URL = os.environ.get("ALEMBIC_TEST_POSTGRES_URL", _DEFAULT_PG_URL)

# A fresh schema must end up with comfortably more than this many public tables;
# the real schema has ~20+. Kept well below the true count so the assertion is a
# robust "the DDL landed" signal, not a brittle exact match.
_MIN_EXPECTED_PUBLIC_TABLES = 15

# Connecting to a down/absent Postgres should fail fast rather than hang the
# whole suite waiting on a TCP timeout.
_CONNECT_TIMEOUT_SECONDS = 5

# Generous ceiling for the subprocess ``alembic upgrade head`` — the full chain
# is fast against a local container but we never want a wedged process to hang
# CI indefinitely.
_UPGRADE_TIMEOUT_SECONDS = 120


def _with_database(url: str, database: str) -> str:
    """Return ``url`` with its path (database name) replaced by ``database``."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def _postgres_reachable() -> bool:
    """True if the base Postgres URL accepts a connection within the timeout."""
    try:
        with psycopg.connect(_BASE_PG_URL, connect_timeout=_CONNECT_TIMEOUT_SECONDS):
            return True
    except psycopg.Error:
        return False


# Skip the whole module when there is no Postgres to talk to. SQLite-only
# environments and CI without a PG service land here and skip cleanly.
pytestmark = pytest.mark.skipif(
    not _postgres_reachable(),
    reason=f"No Postgres reachable at {_BASE_PG_URL} (set ALEMBIC_TEST_POSTGRES_URL)",
)


@pytest.fixture
def scratch_database() -> Iterator[str]:
    """Create a unique throwaway Postgres database and drop it on teardown.

    AUTOCOMMIT is required: ``CREATE DATABASE`` / ``DROP DATABASE`` cannot run
    inside a transaction block. The name is randomized so concurrent test runs
    (or a leftover from a crashed run) never collide.
    """
    db_name = f"alembic_upgrade_test_{uuid.uuid4().hex[:12]}"
    admin = psycopg.connect(_BASE_PG_URL, autocommit=True, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    try:
        admin.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        admin.close()

    try:
        yield db_name
    finally:
        cleanup = psycopg.connect(
            _BASE_PG_URL, autocommit=True, connect_timeout=_CONNECT_TIMEOUT_SECONDS
        )
        try:
            # Terminate any lingering backends so DROP DATABASE never blocks.
            cleanup.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            cleanup.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            cleanup.close()


def _run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run an ``alembic`` subcommand as a subprocess, exactly like production.

    ``DATABASE_URL`` wins over any ``.env`` value (the settings layer reads the
    env var first), so this targets the throwaway database. Running through the
    CLI is deliberate: the bug lives in the connection lifecycle of a real
    ``env.py`` run, which an in-process call would not reproduce faithfully.
    """
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=_UPGRADE_TIMEOUT_SECONDS,
        check=False,
    )


def _expected_head_revision(database_url: str) -> str:
    """Return the migration head Alembic itself reports (``alembic heads``).

    Comparing the stamped revision against Alembic's own notion of head keeps
    the test correct across checkouts/branches (where the head slug differs)
    while still verifying the upgrade ran all the way to the tip.
    """
    result = _run_alembic(database_url, "heads")
    assert result.returncode == 0, f"alembic heads failed:\n{result.stderr}"
    # Output lines look like ``030_drop_user_preferences_default_model_id (head)``.
    for line in result.stdout.splitlines():
        token = line.strip().split()
        if token:
            return token[0]
    raise AssertionError(f"Could not parse a head revision from:\n{result.stdout}")


def _public_table_count(connection: Connection) -> int:
    """Count tables in the ``public`` schema of the connected database."""
    row = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchone()
    assert row is not None
    return int(row[0])


def _alembic_head_revision(connection: Connection) -> str | None:
    """Return the recorded head revision, or None if ``alembic_version`` is absent."""
    exists = connection.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'alembic_version')"
    ).fetchone()
    assert exists is not None
    if not exists[0]:
        return None
    row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def test_alembic_upgrade_head_creates_tables_on_fresh_postgres(scratch_database: str) -> None:
    """A fresh Postgres DB has a populated schema after ``alembic upgrade head``.

    Against the unfixed ``env.py`` the advisory-lock auto-begun transaction is
    rolled back on connection close, so this database would have zero public
    tables and no ``alembic_version`` despite a clean exit-0 upgrade run.
    """
    scratch_url = _with_database(_BASE_PG_URL, scratch_database)
    expected_head = _expected_head_revision(scratch_url)

    result = _run_alembic(scratch_url, "upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade head failed (exit {result.returncode}).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    with psycopg.connect(scratch_url, connect_timeout=_CONNECT_TIMEOUT_SECONDS) as connection:
        table_count = _public_table_count(connection)
        head_revision = _alembic_head_revision(connection)

    # The core regression assertion: DDL was actually committed, not silently
    # rolled back. Pre-fix this is 0.
    assert table_count > _MIN_EXPECTED_PUBLIC_TABLES, (
        f"Expected a populated schema (> {_MIN_EXPECTED_PUBLIC_TABLES} public tables) "
        f"after upgrade, got {table_count}. The advisory-lock auto-begun transaction "
        "was likely rolled back on connection close (the bug this test guards)."
    )

    # Alembic must have stamped the head revision. Pre-fix the table does not
    # even exist (None); post-fix it carries the real head slug (the long
    # ``030_drop_user_preferences_default_model_id`` on the production head,
    # whatever ``alembic heads`` reports on this checkout).
    assert head_revision is not None, "alembic_version table missing — no migration committed"
    assert head_revision == expected_head, (
        f"Recorded revision {head_revision!r} does not match the migration head "
        f"{expected_head!r}; the upgrade did not reach the tip."
    )
