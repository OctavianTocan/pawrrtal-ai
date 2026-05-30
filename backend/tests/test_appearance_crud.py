"""Unit tests for the appearance CRUD service."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.schemas import (
    AppearanceFonts,
    AppearanceOptions,
    AppearanceSettings,
    ThemeColors,
)
from app.workspace.appearance.crud import (
    get_appearance,
    reset_appearance,
    upsert_appearance,
)


@pytest.mark.anyio
async def test_get_returns_none_when_no_row_exists(
    db_session: AsyncSession, test_user: User
) -> None:
    """A user who has never customized appearance returns None (not a stub row)."""
    result = await get_appearance(test_user.id, db_session)
    assert result is None


@pytest.mark.anyio
async def test_upsert_inserts_a_new_row(db_session: AsyncSession, test_user: User) -> None:
    """First upsert creates the 1:1 row with the supplied fields."""
    payload = AppearanceSettings(
        light=ThemeColors(accent="#FF0000", background="#FAF3DF"),
        dark=ThemeColors(accent="#388BFD"),
        fonts=AppearanceFonts(display="Newsreader", sans="Inter"),
        options=AppearanceOptions(theme_mode="dark", contrast=72),
    )

    row = await upsert_appearance(test_user.id, payload, db_session)

    assert row.user_id == test_user.id
    assert row.light == {
        "background": "#FAF3DF",
        "foreground": None,
        "accent": "#FF0000",
        "info": None,
        "success": None,
        "destructive": None,
    }
    assert row.dark is not None and row.dark["accent"] == "#388BFD"
    assert row.fonts is not None and row.fonts["display"] == "Newsreader"
    assert row.options is not None and row.options["theme_mode"] == "dark"
    assert row.options["contrast"] == 72
    assert isinstance(row.updated_at, datetime)


@pytest.mark.anyio
async def test_upsert_replaces_existing_row(db_session: AsyncSession, test_user: User) -> None:
    """Second upsert is a full replacement: omitted sub-fields revert to None."""
    await upsert_appearance(
        test_user.id,
        AppearanceSettings(
            light=ThemeColors(accent="#AAA111"),
            options=AppearanceOptions(contrast=42),
        ),
        db_session,
    )

    updated = await upsert_appearance(
        test_user.id,
        AppearanceSettings(light=ThemeColors(background="#FAF3DF")),
        db_session,
    )

    assert updated.light is not None
    assert updated.light["background"] == "#FAF3DF"
    assert updated.light["accent"] is None
    assert updated.options is not None and updated.options["contrast"] is None


@pytest.mark.anyio
async def test_reset_deletes_persisted_row(db_session: AsyncSession, test_user: User) -> None:
    """Reset removes the row so subsequent gets fall back to defaults."""
    await upsert_appearance(
        test_user.id,
        AppearanceSettings(light=ThemeColors(accent="#FF0000")),
        db_session,
    )
    assert await get_appearance(test_user.id, db_session) is not None

    await reset_appearance(test_user.id, db_session)

    assert await get_appearance(test_user.id, db_session) is None


@pytest.mark.anyio
async def test_reset_is_idempotent_when_no_row_exists(
    db_session: AsyncSession, test_user: User
) -> None:
    """Reset on a user who never customized appearance is a no-op (no error)."""
    await reset_appearance(test_user.id, db_session)
    assert await get_appearance(test_user.id, db_session) is None
