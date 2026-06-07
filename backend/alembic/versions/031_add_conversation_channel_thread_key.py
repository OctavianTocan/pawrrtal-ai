"""Add channel thread keys to conversations.

Revision ID: 031_add_conversation_channel_thread_key
Revises: 030_drop_user_preferences_default_model_id
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "031_add_conversation_channel_thread_key"
down_revision = "030_drop_user_preferences_default_model_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(
            sa.Column("channel_thread_key", sa.String(length=256), nullable=True)
        )
        batch_op.create_index(
            "ix_conversations_channel_scope",
            ["user_id", "origin_channel", "channel_thread_key"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_index("ix_conversations_channel_scope")
        batch_op.drop_column("channel_thread_key")
