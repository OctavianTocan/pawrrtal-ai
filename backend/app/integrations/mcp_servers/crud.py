"""CRUD operations for user-configured external MCP servers (#317).

Plain async-SQLAlchemy helpers. Each function takes ``session`` first
and ``user_id`` second to match the project's CRUD parameter-order
rule.

Config storage is opaque JSON (a string column) at this layer — the
agent-side bridge (see :mod:`app.tools.external_mcp`) is the
single source of truth for the wire shape, so growing new transports
needs no migration.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.models import McpServer


async def list_mcp_servers(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    include_disabled: bool = True,
) -> list[McpServer]:
    """Return every MCP server row owned by ``user_id``.

    ``include_disabled`` defaults to ``True`` (the settings UI wants to
    show paused servers). The agent loop passes ``False`` so the
    cross-provider tool list never sees a disabled server.
    """
    stmt = select(McpServer).where(McpServer.user_id == user_id)
    if not include_disabled:
        stmt = stmt.where(McpServer.status == "enabled")
    stmt = stmt.order_by(McpServer.created_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_mcp_server(
    session: AsyncSession,
    user_id: uuid.UUID,
    server_id: uuid.UUID,
) -> McpServer | None:
    """Return one server row (scoped to the owning user)."""
    stmt = select(McpServer).where(McpServer.user_id == user_id, McpServer.id == server_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_mcp_server(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    config: dict[str, Any],
    status: str = "enabled",
) -> McpServer:
    """Create one MCP server row and return it."""
    now = datetime.now()
    row = McpServer(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        status=status,
        config_json=json.dumps(config, sort_keys=True),
        tools_cache_json=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_mcp_server(
    session: AsyncSession,
    user_id: uuid.UUID,
    server_id: uuid.UUID,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    status: str | None = None,
) -> McpServer | None:
    """Apply a partial update.  Returns the row or ``None`` if missing.

    Toggling ``status`` clears the cached tool inventory so a re-enable
    forces a fresh handshake.
    """
    row = await get_mcp_server(session, user_id, server_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if config is not None:
        row.config_json = json.dumps(config, sort_keys=True)
        row.tools_cache_json = None
    if status is not None and status != row.status:
        row.status = status
        row.tools_cache_json = None
    row.updated_at = datetime.now()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_mcp_server(
    session: AsyncSession,
    user_id: uuid.UUID,
    server_id: uuid.UUID,
) -> bool:
    """Delete one server row.  Returns ``True`` when a row was removed."""
    row = await get_mcp_server(session, user_id, server_id)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


def parse_mcp_config(row: McpServer) -> dict[str, Any]:
    """Decode ``config_json`` to a Python dict, returning ``{}`` on failure.

    Live behind a helper so every caller gets the same defensive
    fallback — a malformed row must never crash the chat router.
    """
    raw = row.config_json or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
