"""Tests for the email-allowlist identity gate (``get_allowed_user``)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User


def _user(email: str) -> User:
    """Build a minimal active User row in-memory (no session needed)."""
    return User(
        id=uuid.uuid4(),
        email=email,
        hashed_password="not-used",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )


@pytest.mark.anyio
async def test_empty_allowlist_lets_everyone_through() -> None:
    """An empty allowlist means the deployment is open (useful for local dev)."""
    stub = SimpleNamespace(allowed_emails_set=frozenset())
    with patch("app.users.settings", stub):
        result = await get_allowed_user(_user("anyone@example.com"))
        assert result.email == "anyone@example.com"


@pytest.mark.anyio
async def test_allowlist_admits_listed_email_case_insensitive() -> None:
    """Listed users get through; matching is case-insensitive."""
    stub = SimpleNamespace(
        allowed_emails_set=frozenset({"tavi@example.com", "esther@example.com"}),
    )
    with patch("app.users.settings", stub):
        result = await get_allowed_user(_user("Tavi@Example.com"))
        assert result.email == "Tavi@Example.com"


@pytest.mark.anyio
async def test_allowlist_blocks_unlisted_email_with_generic_message() -> None:
    """Unlisted users get 403 with a deliberately generic message."""
    stub = SimpleNamespace(allowed_emails_set=frozenset({"tavi@example.com"}))
    with patch("app.users.settings", stub):
        with pytest.raises(HTTPException) as exc_info:
            await get_allowed_user(_user("stranger@example.com"))
        assert exc_info.value.status_code == 403
        # Generic message so a stranger can't enumerate the allowlist.
        assert "private" in exc_info.value.detail.lower()


def test_allowed_emails_set_parses_comma_separated_values() -> None:
    """The settings property splits, strips, and lowercases the env value."""
    from app.core.config import Settings

    # Build a fresh Settings instance with our test value.  Use object.__setattr__
    # so we don't have to bother with the BaseSettings constructor.
    raw = "  Tavi@example.com , esther@example.com,,  "

    class _Stub(Settings):
        model_config = Settings.model_config

    # Pydantic settings requires all required fields; pull from the real
    # settings instance and override just `allowed_emails`.
    from app.core.config import settings as real_settings

    overridden = real_settings.model_copy(update={"allowed_emails": raw})
    assert overridden.allowed_emails_set == frozenset({"tavi@example.com", "esther@example.com"})


def test_allowed_emails_set_is_empty_when_unset() -> None:
    """No env var → empty frozenset → gate is disabled."""
    from app.core.config import settings as real_settings

    overridden = real_settings.model_copy(update={"allowed_emails": ""})
    assert overridden.allowed_emails_set == frozenset()
