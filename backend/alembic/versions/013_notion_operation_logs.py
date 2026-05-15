"""Add the notion_operation_logs audit table.

Revision ID: 013_notion_operation_logs
Revises: 012_canonicalise_conversation_model_ids
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013_notion_operation_logs"
down_revision: str | None = "012_canonicalise_conversation_model_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the audit-log table used by the Notion plugin."""
    op.create_table(
        "notion_operation_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("page_id", sa.String(length=64), nullable=True),
        sa.Column("database_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_notion_operation_logs_workspace_id",
        "notion_operation_logs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_notion_operation_logs_tool_name",
        "notion_operation_logs",
        ["tool_name"],
    )
    op.create_index(
        "ix_notion_operation_logs_page_id",
        "notion_operation_logs",
        ["page_id"],
    )
    op.create_index(
        "ix_notion_operation_logs_database_id",
        "notion_operation_logs",
        ["database_id"],
    )
    op.create_index(
        "ix_notion_operation_logs_created_at",
        "notion_operation_logs",
        ["created_at"],
    )


def downgrade() -> None:
    """Drop the audit table and its indexes."""
    for ix in (
        "ix_notion_operation_logs_created_at",
        "ix_notion_operation_logs_database_id",
        "ix_notion_operation_logs_page_id",
        "ix_notion_operation_logs_tool_name",
        "ix_notion_operation_logs_workspace_id",
    ):
        op.drop_index(ix, table_name="notion_operation_logs")
    op.drop_table("notion_operation_logs")
