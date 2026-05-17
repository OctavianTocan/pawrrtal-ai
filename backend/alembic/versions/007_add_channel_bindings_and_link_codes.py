"""add channel_bindings + channel_link_codes tables

Revision ID: 007_add_channel_bindings
Revises: 006_add_user_personalization
Create Date: 2026-05-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_add_channel_bindings"
down_revision: Union[str, None] = "006_add_user_personalization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the channel_bindings + channel_link_codes tables.

    `channel_bindings` is the persistent map from a third-party messaging
    identity (Telegram user/chat, eventually Slack/WhatsApp) to a Pawrrtal
    user. One row per (provider, external_user_id) pair so the same
    Telegram account can never silently move between Pawrrtal users.

    `channel_link_codes` is the short-lived one-time-use handshake table
    used by the web → bot binding flow: the web app issues a code, the
    user pastes (or deep-links) it to the bot, and the bot consumes the
    row to create the binding.
    """
    op.create_table(
        "channel_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        # Stable identity from the provider — Telegram `user_id` is an int
        # so we store it as text to keep the column provider-agnostic.
        sa.Column("external_user_id", sa.String(length=128), nullable=False),
        # Default chat to use when the bot needs to push to the user
        # outside of an inbound flow (e.g. proactive notifications). For
        # Telegram direct chats this equals external_user_id; for groups
        # it's the chat where the binding was completed.
        sa.Column("external_chat_id", sa.String(length=128), nullable=True),
        # Optional human-readable handle the bot saw at bind time. Stored
        # purely for admin/debug surfaces — never trusted for auth.
        sa.Column("display_handle", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "provider",
            "external_user_id",
            name="uq_channel_bindings_provider_external_user",
        ),
    )

    op.create_table(
        "channel_link_codes",
        # We store an HMAC of the user-facing code so a DB leak alone
        # cannot be replayed. Lookups are by hash, so make it the PK.
        sa.Column("code_hash", sa.String(length=128), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Drop the channel tables."""
    op.drop_table("channel_link_codes")
    op.drop_table("channel_bindings")
