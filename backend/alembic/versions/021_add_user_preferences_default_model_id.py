"""Add ``default_model_id`` column to ``user_preferences``.

Per-user default model selection. When set, this overrides the
catalog default for conversations that don't carry their own
explicit ``model_id``.  Used primarily by the Telegram ``/model``
command so a user can pin a preferred model once and have every
new Telegram conversation default to it.

Revision ID: 021_add_user_preferences_default_model_id
Revises: 020_add_conversation_reasoning_effort
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "021_add_user_preferences_default_model_id"
down_revision = "020_add_conversation_reasoning_effort"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable ``default_model_id`` column."""
    op.add_column(
        "user_preferences",
        sa.Column("default_model_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``default_model_id`` column."""
    op.drop_column("user_preferences", "default_model_id")
