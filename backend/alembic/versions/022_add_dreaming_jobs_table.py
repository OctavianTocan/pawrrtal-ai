"""Add the ``dreaming_jobs`` table for between-sessions reflection (#341).

Per the ADR at
``frontend/content/docs/handbook/decisions/2026-05-20-dreaming-background-reflection.mdx``,
the dreaming pass runs in two modes (session-end + daily cron),
both writing to the same ``DreamingJob`` row. The row records what
the pass was given as input, what the pass produced, and how long
it took — enough to grep operator logs, replay a failed pass, and
trace any memory row back to the pass that created it via
``memories.provenance_job_id``.

Revision ID: 022_add_dreaming_jobs_table
Revises: 021_add_memories_table
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "022_add_dreaming_jobs_table"
down_revision = "021_add_memories_table"
branch_labels = None
depends_on = None

# Allowed values for the ``scope`` discriminator.
# ``session_end`` runs on a single conversation after it goes idle;
# ``daily_rollup`` runs on the user's prior 24h across conversations.
_SCOPE_VALUES = ("session_end", "daily_rollup")

# Allowed values for the ``status`` field.
# ``pending`` — created but not yet started.
# ``running`` — actively reflecting.
# ``completed`` — wrote its outputs successfully.
# ``failed`` — terminal failure (logged + surfaced in /status).
_STATUS_VALUES = ("pending", "running", "completed", "failed")


def upgrade() -> None:
    """Create the dreaming_jobs table and supporting indexes."""
    op.create_table(
        "dreaming_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        # Model used for the reflection. Stored verbatim so a future
        # change to ``settings.dreaming_model`` doesn't rewrite the
        # historical record.
        sa.Column("model_id", sa.String(length=128), nullable=True),
        # Token-bound window the pass actually read. Useful when the
        # 24h dump exceeded the cap and the truncated tail mattered.
        sa.Column("input_token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_token_count", sa.Integer(), nullable=False, server_default="0"),
        # Counts per output category — match the four bucket names
        # from the ADR (consolidated_memories / patterns / followups /
        # session_summary). Stored individually so /status can
        # surface "🌙 last night: 3 memories, 1 follow-up".
        sa.Column("memories_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("patterns_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("followups_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("session_summary", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"scope IN ({', '.join(repr(v) for v in _SCOPE_VALUES)})",
            name="ck_dreaming_jobs_scope_valid",
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(v) for v in _STATUS_VALUES)})",
            name="ck_dreaming_jobs_status_valid",
        ),
    )
    # /status panel asks "what was the last dreaming pass for this
    # user?" — index by (user, created_at desc) to make that cheap.
    op.create_index(
        "ix_dreaming_jobs_user_created_at",
        "dreaming_jobs",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    """Drop the dreaming_jobs table and its index."""
    op.drop_index("ix_dreaming_jobs_user_created_at", table_name="dreaming_jobs")
    op.drop_table("dreaming_jobs")
