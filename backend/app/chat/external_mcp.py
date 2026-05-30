"""External MCP server loader for the chat router (#317).

Pulled out of :mod:`app.chat.router` so the router stays under sentrux's
``no_god_files`` fan-out budget. The function reads the authenticated
user's enabled MCP server rows from the database and projects them
into the shape :func:`app.agents.tools.build_agent_tools` expects.

Any database error is logged and swallowed: a broken row must never
prevent a chat turn from running with the core tool set.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import app.integrations.mcp_servers.crud as mcp_crud

logger = logging.getLogger(__name__)


async def load_external_mcp_configs(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Resolve the user's enabled external MCP server configs."""
    try:
        rows = await mcp_crud.list_mcp_servers(session, user_id, include_disabled=False)
    except Exception:
        logger.exception("MCP_LOAD_FAILED user_id=%s", user_id)
        return []
    return [{"name": row.name, "config": mcp_crud.parse_mcp_config(row)} for row in rows]
