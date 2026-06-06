"""Drop the ``default_model_id`` column from ``user_preferences``.

The per-user default model feature was removed: model selection no
longer falls back to a stored per-user default (it resolves from the
request or the conversation only). This drops the now-unused column
added in migration 022.

Revision ID: 030_drop_user_preferences_default_model_id
Revises: 029
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "030_drop_user_preferences_default_model_id"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_preferences") as batch_op:
        batch_op.drop_column("default_model_id")


def downgrade() -> None:
    with op.batch_alter_table("user_preferences") as batch_op:
        batch_op.add_column(
            sa.Column("default_model_id", sa.String(length=128), nullable=True)
        )
