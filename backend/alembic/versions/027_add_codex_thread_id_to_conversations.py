"""add codex_thread_id to conversations

Revision ID: 027
Revises: 026
Create Date: 2026-05-27

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '027'
down_revision = '026_add_fire_at_to_scheduled_jobs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use batch_alter_table for SQLite compatibility (Alembic's recommended
    # pattern for databases with limited ALTER TABLE support).
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.add_column(
            sa.Column('codex_thread_id', sa.String(length=128), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.drop_column('codex_thread_id')
