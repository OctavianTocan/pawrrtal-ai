"""Add ``reasoning_effort`` column to ``conversations``.

Mirrors ``verbose_level`` (per-conversation streaming knob) — a
nullable VARCHAR(16) holding one of the ``ReasoningEffort`` literal
values (``"low" | "medium" | "high" | "extra-high"``) or NULL to let
the provider pick its default. A chat request may still override per
turn; absent that, the persisted value is what the turn runner
forwards to the provider.

Revision ID: 020_add_conversation_reasoning_effort
Revises: 019_add_lcm_embeddings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "020_add_conversation_reasoning_effort"
down_revision = "019_add_lcm_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable ``reasoning_effort`` column."""
    op.add_column(
        "conversations",
        sa.Column("reasoning_effort", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``reasoning_effort`` column."""
    op.drop_column("conversations", "reasoning_effort")
