"""initial schema — base tables created by the original create_all() call

Revision ID: 000_initial_schema
Revises:
Create Date: 2026-05-11

On the original Railway deployment the tables were bootstrapped via
SQLAlchemy's ``Base.metadata.create_all()`` rather than a migration, so
no initial Alembic revision existed. This migration captures that baseline
so a fresh database (e.g. Docker Compose) can be brought up cleanly via
``alembic upgrade head`` without relying on any pre-existing tables.

Existing deployments that already have the tables created should stamp
this revision as applied before running ``upgrade head``:
    alembic stamp 000_initial_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the base tables that existed before any incremental migrations."""
    # Alembic defaults to VARCHAR(32) for version_num, but several revision IDs
    # in this project exceed that limit. Expand it before any migrations write
    # their revision IDs into the table.
    if op.get_bind().dialect.name != "sqlite":
        op.execute(
            "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"
        )

    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "user_preferences",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column("accent_color", sa.String(length=7), nullable=True),
        sa.Column("font_size", sa.Integer(), nullable=False, server_default="14"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("encrypted_key", sa.String(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("user_preferences")
    op.drop_table("conversations")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_table("user")
