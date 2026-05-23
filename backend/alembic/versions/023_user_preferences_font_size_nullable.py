"""Make ``user_preferences.font_size`` nullable.

NULL means "use the UI default" — the frontend appearance settings
own the canonical default value. Previously the column was NOT NULL
with no schema default, which forced anyone seeding the row on
demand to duplicate the frontend's default literal in Python.

Revision ID: 023_user_preferences_font_size_nullable
Revises: 022_add_user_preferences_default_model_id
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "023_user_preferences_font_size_nullable"
down_revision = "022_add_user_preferences_default_model_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_preferences") as batch_op:
        batch_op.alter_column("font_size", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Back-fill NULL rows before re-applying the NOT NULL constraint —
    # the previous schema had no schema default, so the only thing we
    # can safely re-insert is the historical Python-side seed (14).
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE user_preferences SET font_size = 14 WHERE font_size IS NULL"))
    with op.batch_alter_table("user_preferences") as batch_op:
        batch_op.alter_column("font_size", existing_type=sa.Integer(), nullable=False)
