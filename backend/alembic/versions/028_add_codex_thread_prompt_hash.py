"""add codex_thread_prompt_hash to conversations

Revision ID: 028
Revises: 027
Create Date: 2026-05-31

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column("codex_thread_prompt_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("codex_thread_prompt_hash")
