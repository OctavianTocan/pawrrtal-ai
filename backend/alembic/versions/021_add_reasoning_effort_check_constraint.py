"""Pin ``conversations.reasoning_effort`` to the canonical enum values.

Migration 020 added the column as a free-form ``VARCHAR(16)`` because
the resolver in :mod:`app.core.providers.reasoning` defensively maps
unknown strings to ``cleared``. The DB itself would still accept any
16-char string — typos in future migrations, an admin SQL session, or
an out-of-tree script could plant a row the resolver then has to
silently scrub on every turn.

This migration adds a ``CHECK`` constraint pinning the column to the
four ``ReasoningEffort`` literal values plus ``NULL`` so invalid writes
fail at insert/update time, regardless of where they originate.

Revision ID: 021_add_reasoning_effort_check_constraint
Revises: 020_add_conversation_reasoning_effort
"""

from __future__ import annotations

from alembic import op

revision = "021_add_reasoning_effort_check_constraint"
down_revision = "020_add_conversation_reasoning_effort"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "ck_conversations_reasoning_effort_valid"
# Mirrors ``app.core.providers.base.ReasoningEffort`` literally. Keep
# in sync if the literal grows — the resolver and the DB must agree on
# the set of legal values or one of them will start producing surprises.
_ALLOWED_VALUES = ("minimal", "low", "medium", "high", "extra-high")


def _check_expression() -> str:
    """Render the SQL CHECK predicate for the constraint."""
    quoted = ", ".join(f"'{value}'" for value in _ALLOWED_VALUES)
    return f"reasoning_effort IS NULL OR reasoning_effort IN ({quoted})"


def upgrade() -> None:
    """Reject any row whose ``reasoning_effort`` isn't on the canonical ladder."""
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "conversations",
        _check_expression(),
    )


def downgrade() -> None:
    """Drop the CHECK constraint so the column accepts any 16-char string again."""
    op.drop_constraint(_CONSTRAINT_NAME, "conversations", type_="check")
