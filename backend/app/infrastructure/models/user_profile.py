"""User preference, personalization, and appearance ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from app.infrastructure.models.base import Base


class UserPreferences(Base):
    """User preferences stored in the application database."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    accent_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # NULL = "use the UI default" — the frontend appearance settings
    # own the canonical value, so seed-on-demand CRUD doesn't need to
    # duplicate that literal in Python. Migration 022.
    font_size: Mapped[int | None] = mapped_column(nullable=True)
    # User-level default model. When NULL, conversation model resolution
    # falls back to ``catalog.default_model()``. When set, this is the
    # canonical "host:vendor/model" form picked by the user via the
    # Telegram ``/model ... default`` command or the picker's "Set as
    # default" button.
    default_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class UserPersonalization(Base):
    """Personalization profile filled in by the home-page wizard.

    1:1 with `user`. Every field is nullable so a partial profile (e.g.
    user skipped the ChatGPT-context step) round-trips cleanly through
    GET / PUT without coercing missing fields into empty strings.
    """

    __tablename__ = "user_personalization"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    goals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    connected_channels: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    chatgpt_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class UserAppearance(Base):
    """Per-user theme overrides for the Settings → Appearance panel.

    1:1 with `user`. All fields are JSON blobs so the schema can grow
    (new color slots, new font slots, new behavioral toggles) without a
    migration per addition. Missing keys at the application layer fall
    back to the Mistral-inspired defaults baked into
    ``frontend/app/globals.css`` and mirrored in
    ``frontend/features/appearance/defaults.ts``. A fully empty row
    means "use the system defaults everywhere."

    Light and dark mode are tracked separately because dark mode is
    Codex/GitHub-adjacent in the Pawrrtal design system, not just
    inverted from light.
    """

    __tablename__ = "user_appearance"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    # Per-mode color overrides: { background, foreground, accent, info,
    # success, destructive }. Each value is a CSS color string (hex,
    # `oklch(...)`, etc.) that replaces the corresponding `--<role>` CSS
    # variable on `<html>` for that theme.
    light: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    dark: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Font family overrides: { display, sans, mono }. Each is a raw CSS
    # font-family value (e.g. "Newsreader, Georgia, serif").
    fonts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Mode + global tweaks. See the Pydantic `AppearanceOptions` schema
    # for the canonical shape.
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


__all__ = ["UserAppearance", "UserPersonalization", "UserPreferences"]
