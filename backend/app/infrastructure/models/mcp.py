"""ORM model for user-configured external MCP servers (#317)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models.base import Base


def _utcnow() -> datetime:
    """Return current wall-clock time."""
    return datetime.now()


# TODO: I'm not too sure that this should be a DB model; It feels more like something that should be stored in a text file in the user's workspace.
class McpServer(Base):
    """One user-configured external MCP server.

    Each row stores the configuration the user supplied through the
    settings UI (or via API). The agent loop loads the user's enabled
    servers at turn start and exposes the tools they advertise as
    cross-provider :class:`AgentTool` instances.

    Storage is opaque-JSON on purpose: today's reader understands
    ``{"transport": "http", "url": "...", "headers": {...}}``, but
    future transports (stdio, websocket) can extend the schema
    without a migration.  ``status`` lets the user pause a misbehaving
    server without losing their config; ``tools_cache_json`` caches
    the last-known tool inventory so a cold provider boot doesn't
    have to re-handshake every server.
    """

    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Human-readable identifier the user picked. Unique per user so
    # tool naming (``mcp_<name>_<tool>``) doesn't collide, and the UI
    # can show "Notion" / "GitHub" / ... rather than a raw UUID.
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # One of "enabled" / "disabled". String rather than Enum so the
    # column can grow new values (e.g. "broken") without a migration.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="enabled")
    # Opaque config blob — see class docstring.
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Cached tool inventory from the last successful handshake; NULL
    # before the first call. Cleared on status toggle so a re-enable
    # forces a fresh handshake.
    tools_cache_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


__all__ = ["McpServer"]
