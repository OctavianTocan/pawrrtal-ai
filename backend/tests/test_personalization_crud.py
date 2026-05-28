"""Unit tests for the personalization CRUD service."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.personalization import (
    get_personalization,
    upsert_personalization,
)
from app.infrastructure.database.legacy import User
from app.schemas import PersonalizationProfile


@pytest.mark.anyio
async def test_get_returns_none_when_no_row_exists(
    db_session: AsyncSession, test_user: User
) -> None:
    """A user who has never filled the wizard returns None (not a stub row)."""
    result = await get_personalization(test_user.id, db_session)
    assert result is None


@pytest.mark.anyio
async def test_upsert_inserts_a_new_row(db_session: AsyncSession, test_user: User) -> None:
    """First upsert creates the 1:1 row with the supplied fields."""
    payload = PersonalizationProfile(
        name="Octavian",
        role="Engineering",
        goals=["ship", "talk to users"],
        personality="goose",
    )

    row = await upsert_personalization(test_user.id, payload, db_session)

    assert row.user_id == test_user.id
    assert row.name == "Octavian"
    assert row.role == "Engineering"
    assert row.goals == ["ship", "talk to users"]
    assert row.personality == "goose"
    assert isinstance(row.updated_at, datetime)


@pytest.mark.anyio
async def test_upsert_replaces_existing_row(db_session: AsyncSession, test_user: User) -> None:
    """Second upsert is a full replacement: omitted fields go back to None."""
    await upsert_personalization(
        test_user.id, PersonalizationProfile(name="A", role="X"), db_session
    )

    updated = await upsert_personalization(
        test_user.id, PersonalizationProfile(name="B"), db_session
    )

    assert updated.name == "B"
    assert updated.role is None


@pytest.mark.anyio
async def test_get_returns_persisted_row_after_upsert(
    db_session: AsyncSession, test_user: User
) -> None:
    """After upsert the get-side reads the same payload back."""
    await upsert_personalization(
        test_user.id,
        PersonalizationProfile(name="Tavi", custom_instructions="Be terse."),
        db_session,
    )
    fetched = await get_personalization(test_user.id, db_session)
    assert fetched is not None
    assert fetched.name == "Tavi"
    assert fetched.custom_instructions == "Be terse."
