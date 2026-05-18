"""Add scheduled_jobs.target_conversation_id for cross-channel delivery.

The scheduler + EventBus + AgentHandler pipeline already runs a turn
when a cron job fires and ships the response to Telegram chats via
``target_chat_ids``. The web side has no equivalent — a scheduled
turn vanishes from the UI even when the originating user has the
workspace open.

This column lets a scheduled job (or any future ``ScheduledEvent``
producer) name a single chat conversation to persist the response
into. ``AgentHandler`` reads the field off the event and writes the
generated text into ``chat_messages`` via the existing CRUD before
publishing ``AgentResponseEvent`` for Telegram fan-out.

Nullable + ``ON DELETE SET NULL`` so deleting the target conversation
quietly disables persistence for the job — preferable to cascading
the deletion through to the job row itself.

Revision ID: 018_scheduled_jobs_target_conversation_id
Revises: 017_add_mcp_servers
Create Date: 2026-05-17 22:45:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "018_scheduled_jobs_target_conversation_id"
down_revision = "017_add_mcp_servers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable FK column with an index for fast lookup."""
    op.add_column(
        "scheduled_jobs",
        sa.Column("target_conversation_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_scheduled_jobs_target_conversation_id",
        "scheduled_jobs",
        "conversations",
        ["target_conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_scheduled_jobs_target_conversation_id",
        "scheduled_jobs",
        ["target_conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the index, FK, and column in reverse order."""
    op.drop_index("ix_scheduled_jobs_target_conversation_id", table_name="scheduled_jobs")
    op.drop_constraint(
        "fk_scheduled_jobs_target_conversation_id",
        "scheduled_jobs",
        type_="foreignkey",
    )
    op.drop_column("scheduled_jobs", "target_conversation_id")
