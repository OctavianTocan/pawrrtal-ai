"""add projects table + conversations.project_id FK

Revision ID: 005_add_projects
Revises: 004_add_conversation_labels
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_projects"
down_revision: str | None = "004_add_conversation_labels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the projects table and link conversations.project_id."""
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "project_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "projects.id",
                    ondelete="SET NULL",
                    name="fk_conversations_project_id_projects",
                ),
                nullable=True,
            )
        )
        batch_op.create_index("ix_conversations_project_id", ["project_id"])


def downgrade() -> None:
    """Drop the project_id FK + projects table."""
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_index("ix_conversations_project_id")
        batch_op.drop_column("project_id")
    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")
