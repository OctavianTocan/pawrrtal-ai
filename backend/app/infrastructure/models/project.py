"""Project ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models.base import Base


class Project(Base):
    """Top-level project users can drop conversations into.

    Pure organizational container — has no settings of its own today.
    Conversations point at it via ``Conversation.project_id``; deleting
    the project sets every linked conversation's ``project_id`` back to
    NULL rather than cascading.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


__all__ = ["Project"]
