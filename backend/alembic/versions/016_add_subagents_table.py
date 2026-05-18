"""Add subagents table.

Backs the durable side of the v3 subagent system.  Schema-only — PRs 3
and 4 add the runner and the tools that read and write these rows.

Cascade chain:

  * conversations.id   →  ON DELETE CASCADE     (matches LCM tables)
  * user.id            →  ON DELETE CASCADE
  * chat_messages.id   →  ON DELETE SET NULL    (placeholder finalises
                                                  asynchronously)
  * subagents.id       →  ON DELETE CASCADE     (deleting a parent
                                                  removes descendants
                                                  atomically — keeps
                                                  the depth cap honest)

Status column is a plain String(16) — not a DB ENUM — so the same
schema runs on SQLite (tests) and Postgres (prod) without an ALTER
TYPE pain point.  The Python-side ``SubagentStatus`` literal in
``app.subagent_models`` is the type-safe gate.

Revision ID: 016_add_subagents_table
Revises: 015_add_lcm_tables
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "016_add_subagents_table"
down_revision = "015_add_lcm_tables"
branch_labels = None
depends_on = None


# Column-width named constants — kept in lockstep with
# ``backend/app/subagent_models.py``.  Mismatched widths between the
# migration and the ORM model are caught by the migration test in
# ``backend/tests/test_subagent_crud.py``.
_STATUS_COL_LEN: int = 16
_PERSONA_NAME_COL_LEN: int = 64
_HANDLE_COL_LEN: int = 80
_LABEL_COL_LEN: int = 200


def upgrade() -> None:
    """Create the ``subagents`` table and its supporting indices."""
    op.create_table(
        "subagents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("parent_user_id", sa.Uuid(), nullable=False),
        sa.Column("parent_message_id", sa.Uuid(), nullable=True),
        sa.Column("parent_subagent_id", sa.Uuid(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("persona_name", sa.String(length=_PERSONA_NAME_COL_LEN), nullable=False),
        sa.Column("handle", sa.String(length=_HANDLE_COL_LEN), nullable=False),
        sa.Column("label", sa.String(length=_LABEL_COL_LEN), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=_STATUS_COL_LEN),
            nullable=False,
            server_default="running",
        ),
        # SQLAlchemy's JSON portable type — works on SQLite (tests) and
        # Postgres (prod); the LCM tables use Postgres JSONB but those
        # were inherited from upstream.  Plain JSON is fine here: we
        # only filter by FK + status, never by tools_granted contents.
        sa.Column(
            "tools_granted",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spawned_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_subagent_id"], ["subagents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handle", name="uq_subagents_handle"),
    )
    # Auto-index from UNIQUE on handle; no need for a separate index.
    op.create_index(
        "ix_subagents_conversation_id",
        "subagents",
        ["conversation_id"],
    )
    op.create_index(
        "ix_subagents_conversation_status",
        "subagents",
        ["conversation_id", "status"],
    )


def downgrade() -> None:
    """Drop the ``subagents`` table and its indices."""
    op.drop_index("ix_subagents_conversation_status", table_name="subagents")
    op.drop_index("ix_subagents_conversation_id", table_name="subagents")
    op.drop_table("subagents")
