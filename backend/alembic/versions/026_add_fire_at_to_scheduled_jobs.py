"""Add fire_at to scheduled_jobs table for one-shot reminders.

Revision ID: 026_add_fire_at_to_scheduled_jobs
Revises: 025_add_dreaming_jobs_table
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "026_add_fire_at_to_scheduled_jobs"
down_revision = "025_add_dreaming_jobs_table"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add fire_at column.
    with op.batch_alter_table("scheduled_jobs") as batch_op:
        batch_op.add_column(sa.Column("fire_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column("cron_expression", existing_type=sa.String(128), nullable=True)

def downgrade() -> None:
    with op.batch_alter_table("scheduled_jobs") as batch_op:
        batch_op.alter_column("cron_expression", existing_type=sa.String(128), nullable=False)
        batch_op.drop_column("fire_at")
