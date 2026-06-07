"""Replace provider-specific conversation session columns.

Revision ID: 032_generic_provider_sessions
Revises: 031_add_conversation_channel_thread_key
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "032_generic_provider_sessions"
down_revision = "031_add_conversation_channel_thread_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column("provider_session_kind", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("provider_session_id", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column("provider_session_fingerprint", sa.String(length=128), nullable=True)
        )

    op.execute(
        """
        UPDATE conversations
        SET
            provider_session_kind = 'agy_cli',
            provider_session_id = agy_conversation_id
        WHERE agy_conversation_id IS NOT NULL
          AND (model_id LIKE 'agy-api:%' OR model_id LIKE 'agy-cli:%')
        """
    )
    op.execute(
        """
        UPDATE conversations
        SET
            provider_session_kind = 'openai_codex',
            provider_session_id = codex_thread_id,
            provider_session_fingerprint = codex_thread_prompt_hash
        WHERE provider_session_id IS NULL
          AND codex_thread_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE conversations
        SET
            provider_session_kind = 'agy_cli',
            provider_session_id = agy_conversation_id
        WHERE provider_session_id IS NULL
          AND agy_conversation_id IS NOT NULL
        """
    )

    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("codex_thread_id")
        batch_op.drop_column("codex_thread_prompt_hash")
        batch_op.drop_column("agy_conversation_id")


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column("agy_conversation_id", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column("codex_thread_prompt_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("codex_thread_id", sa.String(length=128), nullable=True))

    op.execute(
        """
        UPDATE conversations
        SET
            codex_thread_id = provider_session_id,
            codex_thread_prompt_hash = provider_session_fingerprint
        WHERE provider_session_kind = 'openai_codex'
        """
    )
    op.execute(
        """
        UPDATE conversations
        SET agy_conversation_id = provider_session_id
        WHERE provider_session_kind = 'agy_cli'
        """
    )

    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("provider_session_fingerprint")
        batch_op.drop_column("provider_session_id")
        batch_op.drop_column("provider_session_kind")
