"""Add LCM embeddings table for semantic retrieval (issue #254).

Adds ``lcm_embeddings``: one row per ``(conversation_id, item_kind,
item_id, embedding_model)``.  Stores the embedding as a JSON array
rather than pulling in pgvector so the migration stays portable
across SQLite (tests) and Postgres (production).  A future migration
can drop in a real vector column without changing the row layout.

Revision ID: 016_add_lcm_embeddings
Revises: 015_add_lcm_tables
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "016_add_lcm_embeddings"
down_revision = "015_add_lcm_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the lcm_embeddings table and its supporting indices."""
    op.create_table(
        "lcm_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("item_kind", sa.String(length=16), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "item_kind",
            "item_id",
            "embedding_model",
            name="uq_lcm_embeddings_conv_kind_item_model",
        ),
    )
    op.create_index(
        "ix_lcm_embeddings_conversation_id",
        "lcm_embeddings",
        ["conversation_id"],
    )
    op.create_index(
        "ix_lcm_embeddings_item_id",
        "lcm_embeddings",
        ["item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_lcm_embeddings_item_id", table_name="lcm_embeddings")
    op.drop_index("ix_lcm_embeddings_conversation_id", table_name="lcm_embeddings")
    op.drop_table("lcm_embeddings")
