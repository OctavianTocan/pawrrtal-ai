"""Validators and derived properties for :class:`Settings`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self
from urllib.parse import urlparse

from pydantic import field_validator, model_validator

from app.infrastructure.config_urls import (
    async_database_url,
    normalize_database_url,
    sync_database_url,
)


class SettingsBehaviorMixin:
    """Pydantic validators and computed fields split from ``config.py``."""

    if TYPE_CHECKING:
        claude_sandbox_excluded_commands: str
        voice_max_size_mb: int
        cookie_secure: bool | None
        cookie_samesite: Literal["lax", "strict", "none"]
        env: str
        database_url: str
        sqlite_db_filename: str

    @property
    def claude_sandbox_excluded_commands_list(self) -> list[str]:
        """Parsed view of ``claude_sandbox_excluded_commands``."""
        if not self.claude_sandbox_excluded_commands:
            return []
        return [
            cmd.strip() for cmd in self.claude_sandbox_excluded_commands.split(",") if cmd.strip()
        ]

    @property
    def voice_max_size_bytes(self) -> int:
        """Voice size cap in bytes (the handler validates against this)."""
        bytes_per_mb = 1024 * 1024
        return self.voice_max_size_mb * bytes_per_mb

    @field_validator("telegram_bot_username", mode="before")
    @classmethod
    def _strip_telegram_at_prefix(cls, value: object) -> object:
        """Forgive a leading ``@`` in ``TELEGRAM_BOT_USERNAME``.

        Telegram deep links are ``https://t.me/<username>``; an ``@``
        produces ``t.me/@username`` which Telegram redirects to its
        homepage instead of the bot. Humans frequently paste the
        ``@``-prefixed handle into ``.env``, so we normalize once at the
        config boundary instead of forcing every consumer to remember.
        """
        if isinstance(value, str):
            return value.lstrip("@")
        return value

    @field_validator("telegram_verbose_default", mode="before")
    @classmethod
    def _coerce_telegram_verbose_default(cls, value: object) -> object:
        """Coerce env-file string values before Literal validation."""
        if isinstance(value, str) and value.strip() in {"0", "1", "2"}:
            return int(value)
        return value

    @field_validator("workspace_base_dir", mode="after")
    @classmethod
    def _expand_workspace_base_dir(cls, value: str) -> str:
        """Expand home-relative workspace roots from env files."""
        return str(Path(value).expanduser())

    @model_validator(mode="after")
    def validate_secure_cookie(self) -> Self:
        """Reject misconfigurations where ``SameSite=none`` is paired with insecure cookies."""
        secure = self.cookie_secure if self.cookie_secure is not None else self.is_production
        if self.cookie_samesite == "none" and not secure:
            raise ValueError(
                "cookie_samesite='none' requires HTTPS (cookie_secure must be True, or run with ENV=prod)."
            )
        return self

    @property
    def is_production(self) -> bool:
        """A convenience property that returns True if the application is running in production mode (i.e., if env is set to "prod")."""
        return self.env == "prod"

    @property
    def _normalized_database_url(self) -> str:
        """Return the configured database URL in a normalized form."""
        return normalize_database_url(self.database_url, self.sqlite_db_filename)

    @property
    def is_sqlite(self) -> bool:
        """Whether the configured database uses SQLite."""
        return urlparse(self._normalized_database_url).scheme.startswith("sqlite")

    @property
    def db_url_sync(self) -> str:
        """Return the database URL formatted for synchronous connections.

        PostgreSQL URLs are normalized to the installed psycopg driver, while
        SQLite async URLs are converted back to the sync sqlite dialect.
        """
        return sync_database_url(self._normalized_database_url)

    @property
    def db_url_async(self) -> str:
        """Return the database URL formatted for asynchronous connections.

        PostgreSQL URLs are normalized to the psycopg async dialect and SQLite
        sync URLs are converted to the aiosqlite dialect.
        """
        return async_database_url(self._normalized_database_url)
