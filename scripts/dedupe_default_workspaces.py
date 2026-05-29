#!/usr/bin/env python3
"""One-shot script to remove duplicate default-workspace rows.

Run this BEFORE applying the 009_unique_default_workspace_per_user Alembic
migration on any database that already has rows (i.e. any deployed instance
that has ever run the onboarding flow).

On a brand-new database the migration is safe to apply without this script.

Usage
-----
    python scripts/dedupe_default_workspaces.py [--dry-run] [--db-url URL]

Options
-------
    --dry-run   Print what would be deleted without touching the database.
    --db-url    SQLAlchemy database URL (defaults to $DATABASE_URL or the
                app's configured DB URL).

Strategy
--------
For each user that has more than one workspace with is_default=True:
  - Keep the row with the latest ``created_at`` timestamp (most complete
    seed, closest to the last onboarding submission).
  - Delete all earlier duplicates.
  - Optionally remove the orphaned workspace directories from the filesystem.

Exit codes
----------
    0  — success (or dry-run with no errors)
    1  — one or more users had un-resolvable duplicates (check logs)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Sync SQLAlchemy (this script runs outside uvicorn, no async required)
# ---------------------------------------------------------------------------

import sqlalchemy as sa
from sqlalchemy import create_engine, text


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="Show what would be deleted without changing anything.")
    p.add_argument("--db-url", default="", help="SQLAlchemy DB URL. Falls back to DATABASE_URL env var.")
    p.add_argument("--remove-dirs", action="store_true", help="Also delete orphaned workspace directories from disk.")
    return p.parse_args()


def get_db_url(args: argparse.Namespace) -> str:
    url = args.db_url or os.environ.get("DATABASE_URL", "")
    if not url:
        # Try to load from app config as last resort.
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
            from app.infrastructure.config import settings  # type: ignore[import]
            url = str(settings.database_url)
        except Exception as exc:
            print(f"ERROR: Could not determine database URL: {exc}", file=sys.stderr)
            sys.exit(1)
    return url


def main() -> None:
    args = parse_args()
    db_url = get_db_url(args)

    # Strip async driver prefix if present (asyncpg → psycopg2, aiosqlite → sqlite).
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "sqlite+aiosqlite:///", "sqlite:///"
    )

    engine = create_engine(sync_url, echo=False)

    with engine.connect() as conn:
        # Find all users with more than one default workspace.
        dupes = conn.execute(
            text(
                """
                SELECT user_id, COUNT(*) AS cnt
                FROM workspaces
                WHERE is_default = true
                GROUP BY user_id
                HAVING COUNT(*) > 1
                """
            )
        ).fetchall()

        if not dupes:
            print("No duplicate default workspaces found. Nothing to do.")
            return

        print(f"Found {len(dupes)} user(s) with duplicate default workspaces.\n")
        errors = 0

        for row in dupes:
            user_id = row[0]
            count = row[1]

            # Fetch all default workspaces for this user, newest first.
            ws_rows = conn.execute(
                text(
                    """
                    SELECT id, path, created_at
                    FROM workspaces
                    WHERE user_id = :uid AND is_default = true
                    ORDER BY created_at DESC
                    """
                ),
                {"uid": user_id},
            ).fetchall()

            keeper = ws_rows[0]
            victims = ws_rows[1:]

            print(
                f"User {user_id}: {count} default workspaces "
                f"→ keeping {keeper[0]} (created {keeper[2]})"
            )
            for v in victims:
                print(f"  {'[DRY RUN] ' if args.dry_run else ''}DELETE id={v[0]}  path={v[1]}")

                if not args.dry_run:
                    try:
                        conn.execute(
                            text("DELETE FROM workspaces WHERE id = :id"),
                            {"id": v[0]},
                        )
                        print(f"    ✓ deleted DB row {v[0]}")
                    except Exception as exc:
                        print(f"    ✗ ERROR deleting {v[0]}: {exc}", file=sys.stderr)
                        errors += 1
                        continue

                if args.remove_dirs:
                    victim_path = Path(v[1])
                    if victim_path.exists():
                        if args.dry_run:
                            print(f"    [DRY RUN] would remove directory: {victim_path}")
                        else:
                            try:
                                shutil.rmtree(victim_path)
                                print(f"    ✓ removed directory {victim_path}")
                            except Exception as exc:
                                print(f"    ✗ ERROR removing {victim_path}: {exc}", file=sys.stderr)
                                errors += 1
                    else:
                        print(f"    (directory already absent: {victim_path})")

        if not args.dry_run:
            conn.commit()
            print("\nCommitted.")

        if errors:
            print(f"\n{errors} error(s) encountered. Check output above.", file=sys.stderr)
            sys.exit(1)
        else:
            action = "Would delete" if args.dry_run else "Deleted"
            total_victims = sum(row[1] - 1 for row in dupes)
            print(f"\n{action} {total_victims} duplicate row(s) across {len(dupes)} user(s).")


if __name__ == "__main__":
    main()
