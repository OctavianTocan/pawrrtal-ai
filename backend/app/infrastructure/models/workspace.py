"""Workspace ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models.base import Base
from app.infrastructure.models.common import utcnow


class Workspace(Base):
    """An agent workspace.

    A named directory on the host filesystem containing the standard
    Pawrrtal workspace structure: root prompt files plus internal
    ``.agent`` memory, protocols, harness, tools, and skills.

    One user can own many workspaces. The first workspace created for a user
    is flagged ``is_default=True`` and seeded automatically at the end of the
    onboarding flow using the user's ``UserPersonalization`` data.

    The ``path`` column is the absolute path on the host. Agents that need
    filesystem access resolve the path from here rather than constructing it
    ad-hoc from the user ID.
    """

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Human-readable label shown in the UI (e.g. "Main", "Work", "Personal").
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Main")
    # Filesystem-safe slug used only as a readable hint alongside the UUID path.
    slug: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    # Absolute path to the workspace root directory on the host.
    path: Mapped[str] = mapped_column(String(4096), nullable=False)
    # Exactly one workspace per user should be the default at any given time.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


__all__ = ["Workspace"]
