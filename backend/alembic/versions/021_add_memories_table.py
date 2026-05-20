"""Add the ``memories`` table for proactive memory writes (#340).

Per the ADR at
``frontend/content/docs/handbook/decisions/2026-05-20-proactive-memory-updates.mdx``,
the chat router runs a post-turn classifier that captures user
preferences, project decisions, and explicit feedback as typed
memory rows.  Those rows live on this table.

The dreaming pass (#341) writes into the same table — the
``source`` column distinguishes per-turn classifier writes from
the dreaming consolidation pass, and ``provenance_job_id`` lets a
reviewer trace any dreaming-written row back to the job that
produced it.

Embeddings are stored as opaque bytes (the existing
``backend/app/core/lcm/embeddings.py`` pipeline does its own
serialisation per provider). A future migration can promote the
column to ``pgvector`` once the operator deployment confirms the
extension is installed.

Revision ID: 021_add_memories_table
Revises: 020_add_conversation_reasoning_effort
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "021_add_memories_table"
down_revision = "020_add_conversation_reasoning_effort"
branch_labels = None
depends_on = None

# Allowed values for the ``kind`` discriminator. Mirrors the literal
# union the application layer uses; pinned via CHECK so an out-of-tree
# script or admin SQL session can't write a garbage value.
_KIND_VALUES = ("feedback", "project", "user")

# Allowed values for the ``source`` provenance flag. ``classifier``
# is the per-turn writer from this ADR; ``dreaming`` is the
# between-sessions consolidation pass (#341); ``user`` is for the
# rare case the user adds a memory manually via the (future) CLI.
_SOURCE_VALUES = ("classifier", "dreaming", "user")


def upgrade() -> None:
    """Create the memories table and supporting indexes."""
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="classifier"),
        sa.Column("provenance_job_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_referenced_at", sa.DateTime(timezone=True), nullable=True),
        # fastapi-users names the user table ``user`` (singular) — not
        # ``users`` — so every cross-table FK uses that. Workspace
        # uses ``workspaces``; see ``__tablename__`` in models.py.
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["chat_messages.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"kind IN ({', '.join(repr(v) for v in _KIND_VALUES)})",
            name="ck_memories_kind_valid",
        ),
        sa.CheckConstraint(
            f"source IN ({', '.join(repr(v) for v in _SOURCE_VALUES)})",
            name="ck_memories_source_valid",
        ),
    )
    # Reading top-K memories by (user, kind) is the hot path for the
    # system-prompt assembler — one composite index gets us both
    # filters at once.
    op.create_index(
        "ix_memories_user_kind",
        "memories",
        ["user_id", "kind"],
    )
    op.create_index(
        "ix_memories_conversation_id",
        "memories",
        ["conversation_id"],
    )


def downgrade() -> None:
    """Drop the memories table and its indexes."""
    op.drop_index("ix_memories_conversation_id", table_name="memories")
    op.drop_index("ix_memories_user_kind", table_name="memories")
    op.drop_table("memories")
