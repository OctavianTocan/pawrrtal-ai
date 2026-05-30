"""Tests for the ``mcp_servers`` CRUD helpers (#317)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.infrastructure.database.legacy import User
from app.integrations.mcp_servers import crud

pytestmark = pytest.mark.anyio


async def test_list_returns_empty_for_user_with_no_servers(
    db_session: AsyncSession, test_user: User
) -> None:
    rows = await crud.list_mcp_servers(db_session, test_user.id)
    assert rows == []


async def test_create_then_list_round_trip(db_session: AsyncSession, test_user: User) -> None:
    created = await crud.create_mcp_server(
        db_session,
        test_user.id,
        name="notion",
        config={"transport": "http", "url": "https://mcp.example.com"},
    )
    assert created.name == "notion"
    assert created.status == "enabled"

    rows = await crud.list_mcp_servers(db_session, test_user.id)
    assert [row.name for row in rows] == ["notion"]


async def test_update_changes_config_and_clears_cache(
    db_session: AsyncSession, test_user: User
) -> None:
    created = await crud.create_mcp_server(
        db_session,
        test_user.id,
        name="github",
        config={"transport": "http", "url": "https://gh.example.com"},
    )
    # Simulate a cached inventory.
    created.tools_cache_json = '{"tools": ["x"]}'
    db_session.add(created)
    await db_session.commit()

    updated = await crud.update_mcp_server(
        db_session,
        test_user.id,
        created.id,
        config={"transport": "http", "url": "https://gh.new.example.com"},
    )
    assert updated is not None
    assert updated.tools_cache_json is None
    assert "gh.new.example.com" in updated.config_json


async def test_update_status_clears_cache(db_session: AsyncSession, test_user: User) -> None:
    created = await crud.create_mcp_server(
        db_session,
        test_user.id,
        name="github",
        config={},
    )
    created.tools_cache_json = '{"tools": []}'
    db_session.add(created)
    await db_session.commit()

    updated = await crud.update_mcp_server(db_session, test_user.id, created.id, status="disabled")
    assert updated is not None
    assert updated.status == "disabled"
    assert updated.tools_cache_json is None


async def test_list_excludes_disabled_when_requested(
    db_session: AsyncSession, test_user: User
) -> None:
    await crud.create_mcp_server(
        db_session, test_user.id, name="enabled-srv", config={}, status="enabled"
    )
    await crud.create_mcp_server(
        db_session, test_user.id, name="disabled-srv", config={}, status="disabled"
    )

    rows = await crud.list_mcp_servers(db_session, test_user.id, include_disabled=False)
    assert [row.name for row in rows] == ["enabled-srv"]


async def test_delete_removes_row(db_session: AsyncSession, test_user: User) -> None:
    created = await crud.create_mcp_server(db_session, test_user.id, name="temp", config={})
    removed = await crud.delete_mcp_server(db_session, test_user.id, created.id)
    assert removed is True
    assert await crud.get_mcp_server(db_session, test_user.id, created.id) is None


async def test_delete_returns_false_when_missing(db_session: AsyncSession, test_user: User) -> None:
    removed = await crud.delete_mcp_server(db_session, test_user.id, uuid.uuid4())
    assert removed is False


async def test_parse_mcp_config_returns_dict(db_session: AsyncSession, test_user: User) -> None:
    row = await crud.create_mcp_server(
        db_session,
        test_user.id,
        name="srv",
        config={"transport": "http", "url": "https://x"},
    )
    parsed = crud.parse_mcp_config(row)
    assert parsed["transport"] == "http"


async def test_parse_mcp_config_returns_empty_on_invalid_json(
    db_session: AsyncSession, test_user: User
) -> None:
    row = await crud.create_mcp_server(db_session, test_user.id, name="srv", config={})
    row.config_json = "not json"
    db_session.add(row)
    await db_session.commit()
    assert crud.parse_mcp_config(row) == {}
