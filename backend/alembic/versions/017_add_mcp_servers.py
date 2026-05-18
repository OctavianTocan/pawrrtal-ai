"""Add ``mcp_servers`` table for user-configured external MCP servers (#317).

Each row stores one MCP server configuration owned by a user. The
agent loop loads the user's enabled servers at turn start and exposes
their discovered tools as cross-provider :class:`AgentTool`s.

Storage shape:

* ``config_json`` — full server config as opaque JSON. Today's reader
  understands ``{"transport": "http", "url": "...", "headers": {...}}``;
  future transports (stdio, ws) extend the schema without a migration.
* ``status`` — one of ``"enabled"`` / ``"disabled"`` so the user can
  pause a misbehaving server without deleting their config.
* ``tools_cache_json`` — last-known tool inventory cached per row so a
  cold provider boot doesn't have to re-handshake every server.
  Cleared (set to ``NULL``) when ``status`` toggles.

Revision ID: 017_add_mcp_servers
Revises: 016_merge_notion_into_lcm_lineage
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "017_add_mcp_servers"
down_revision = "016_merge_notion_into_lcm_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the ``mcp_servers`` table + supporting indices."""
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="enabled"),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("tools_cache_json", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_mcp_servers_user_name"),
    )
    op.create_index(
        "ix_mcp_servers_user_id",
        "mcp_servers",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_servers_user_id", table_name="mcp_servers")
    op.drop_table("mcp_servers")
