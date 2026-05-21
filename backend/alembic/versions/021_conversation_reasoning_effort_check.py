"""Pin ``conversations.reasoning_effort`` to the literal value set (#367).

The column was added by 020 as a nullable ``VARCHAR(16)`` with no value
constraint, but every legitimate writer goes through the
``ReasoningEffort`` literal (``"minimal" | "low" | "medium" | "high" |
"extra-high"``).  The CRUD setter still accepts ``str | None``, which
means a typo or stale enum value would silently land in the database and
break provider resolution at request time.

This migration adds a CHECK constraint that mirrors the literal so the
DB rejects bad values at write time.  NULL is explicitly allowed (SQL
CHECK treats NULL as passing, which matches the "let the provider pick"
sentinel the column already documents).

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
_ALLOWED_VALUES = ("minimal", "low", "medium", "high", "extra-high")


def upgrade() -> None:
    """Add the CHECK constraint pinning ``reasoning_effort`` values."""
    values_sql = ", ".join(f"'{v}'" for v in _ALLOWED_VALUES)
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "conversations",
        f"reasoning_effort IN ({values_sql})",
    )


def downgrade() -> None:
    """Drop the CHECK constraint."""
    op.drop_constraint(_CONSTRAINT_NAME, "conversations", type_="check")
