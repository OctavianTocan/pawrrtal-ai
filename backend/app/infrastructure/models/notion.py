"""Notion plugin audit-log ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from app.infrastructure.models.base import Base
from app.infrastructure.models.common import utcnow


class NotionOperationLog(Base):
    """One row per tool call made by the Notion plugin.

    The Notion plugin shells out to the official ``ntn`` CLI; recording
    each invocation here lets the agent (via ``notion_logs_read``) and
    operators answer "what did this workspace do in Notion lately?"
    without scraping uvicorn logs. Mirrors the SQLite schema used by
    openclaw-notion's ``audit.ts`` so prompts written against that
    contract Just Work here.

    Rows are workspace-scoped: the FK cascades on workspace delete so
    a workspace removal sweeps its history with it.
    """

    __tablename__ = "notion_operation_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Tool that produced this row. E.g. "notion_search", "notion_create".
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Coarse operation bucket — "search", "read", "write", "delete", etc.
    # Useful when a single tool has multiple call shapes.
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    # Page / database / block IDs the call targeted, when known. NULL when
    # the call was workspace-wide (search) or not page-scoped.
    page_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    database_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # "ok" | "error" — outcome string. Mirrored from openclaw-notion's
    # contract so log-reader prompts portable between hosts.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Wall-clock duration of the underlying ntn subprocess call.
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ntn stderr or thrown exception message; NULL on success.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw request / response JSON for debugging. Stored even on success
    # because Notion's API surfaces are wide enough that grepping
    # human-readable history is genuinely useful.
    request_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )


__all__ = ["NotionOperationLog"]
