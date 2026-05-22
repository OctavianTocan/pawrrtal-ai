"""Pin ``conversations.reasoning_effort`` to the literal value set (#367).

The column was added by 020 as a nullable ``VARCHAR(16)`` with no value
constraint, but every legitimate writer goes through the
``ReasoningEffort`` literal (``"minimal" | "low" | "medium" | "high" |
"extra-high"``).  The CRUD setter still accepts ``str | None``, which
means a typo or stale enum value would silently land in the database and
break provider resolution at request time.

This migration:

1. Backfills any pre-existing rows whose ``reasoning_effort`` is outside
   the literal set to NULL. Without this PostgreSQL's immediate validation
   of the new CHECK would abort ``alembic upgrade`` on a single stale row
   from the unconstrained window between 020 and 021.
2. Adds a CHECK constraint that mirrors the literal so the DB rejects
   bad values at write time going forward.

NULL is explicitly allowed (SQL CHECK treats NULL as passing, which
matches the "let the provider pick" sentinel the column already documents).
``op.batch_alter_table`` is used so the constraint addition succeeds on
SQLite as well as Postgres — SQLite does not support ``ALTER TABLE ADD
CONSTRAINT`` directly and needs Alembic's table-recreate fallback.

Revision ID: 021_conversation_reasoning_effort_check
Revises: 020_add_conversation_reasoning_effort
"""

from __future__ import annotations

from alembic import op

revision = "021_conversation_reasoning_effort_check"
down_revision = "020_add_conversation_reasoning_effort"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "ck_conversations_reasoning_effort_values"
# NOTE: must stay in sync with the ``ReasoningEffort`` literal in
# ``app/core/providers/base.py`` and ``_REASONING_EFFORT_VALUES`` on the
# ``Conversation`` model in ``app/models.py``. Migrations can't import
# application code, so the values are intentionally duplicated here —
# adding a new literal value means touching all three sites.
_ALLOWED_VALUES = ("minimal", "low", "medium", "high", "extra-high")


def _values_in_sql() -> str:
    """Return the SQL ``IN (...)`` body for the allowed value set."""
    return ", ".join(f"'{v}'" for v in _ALLOWED_VALUES)


def upgrade() -> None:
    """Backfill stale rows then add the CHECK constraint."""
    values_sql = _values_in_sql()
    # 1) Clear any value that already drifted outside the literal set
    #    so the new CHECK doesn't abort on existing rows. NULL is the
    #    documented "let the provider pick" sentinel and is the only
    #    safe fallback that doesn't pretend to know the user's intent.
    op.execute(
        f"UPDATE conversations SET reasoning_effort = NULL "
        f"WHERE reasoning_effort IS NOT NULL "
        f"AND reasoning_effort NOT IN ({values_sql})"
    )
    # 2) Add the constraint inside a batch block so Alembic recreates
    #    the table on SQLite (which can't ALTER ADD CONSTRAINT) and
    #    runs a plain ALTER on Postgres.
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.create_check_constraint(
            _CONSTRAINT_NAME,
            f"reasoning_effort IN ({values_sql})",
        )


def downgrade() -> None:
    """Drop the CHECK constraint."""
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_constraint(_CONSTRAINT_NAME, type_="check")
