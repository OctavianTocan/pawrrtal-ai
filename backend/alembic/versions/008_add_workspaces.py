"""add workspaces table

Revision ID: 008_add_workspaces
Revises: 007_add_user_appearance
Create Date: 2026-05-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_add_workspaces"
down_revision: Union[str, None] = "007_add_user_appearance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the workspaces table.

    One user can own many workspaces.  Each workspace is a named agent home
    directory on the host filesystem following the Pawrrtal workspace layout
    (root prompt files plus internal memory, protocols, harness, tools, and
    skills under ``.agent``).

    The ``path`` column stores the absolute filesystem path so agents and API
    endpoints can resolve files without reconstructing the path from user IDs.

    ``is_default`` flags the workspace that was created at onboarding — users
    start with exactly one default workspace; additional workspaces (work,
    personal, project-specific, etc.) are created on demand and have
    ``is_default=False``.
    """
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default="Main"),
        sa.Column("slug", sa.String(255), nullable=False, server_default="main"),
        sa.Column("path", sa.String(4096), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_workspaces_user_id", table_name="workspaces")
    op.drop_table("workspaces")
