"""HTTP endpoints for user-configured external MCP servers (#317).

CRUD over the ``mcp_servers`` table. Every endpoint is scoped to the
authenticated user — the CRUD helpers take ``user_id`` so a user can
only see / mutate their own rows.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.integrations.mcp_servers import crud
from app.models import McpServer

log = logging.getLogger(__name__)


class McpServerPayload(BaseModel):
    """Request body for create / update endpoints.

    ``config`` is opaque JSON; the bridge in
    :mod:`app.tools.external_mcp` is the single source of truth
    for the wire shape.
    """

    name: str = Field(..., min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="enabled", pattern=r"^(enabled|disabled)$")


class McpServerResponse(BaseModel):
    """Response body for list / read / write endpoints."""

    id: uuid.UUID
    name: str
    status: str
    config: dict[str, Any]


def _to_response(row: McpServer) -> McpServerResponse:
    """Project an ORM row into the API response shape."""
    return McpServerResponse(
        id=row.id,
        name=row.name,
        status=row.status,
        config=crud.parse_mcp_config(row),
    )


def get_mcp_servers_router() -> APIRouter:
    """Build the MCP-servers router (mounted at /api/v1/mcp/servers)."""
    router = APIRouter(prefix="/api/v1/mcp/servers", tags=["mcp"])

    @router.get("", response_model=list[McpServerResponse])
    async def list_servers(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> list[McpServerResponse]:
        """Return every MCP server configured by the authenticated user."""
        rows = await crud.list_mcp_servers(session, user.id)
        return [_to_response(row) for row in rows]

    @router.post("", response_model=McpServerResponse, status_code=201)
    async def create_server(
        payload: McpServerPayload,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> McpServerResponse:
        """Create one MCP server row owned by the authenticated user."""
        row = await crud.create_mcp_server(
            session,
            user.id,
            name=payload.name,
            config=payload.config,
            status=payload.status,
        )
        return _to_response(row)

    @router.patch("/{server_id}", response_model=McpServerResponse)
    async def update_server(
        server_id: uuid.UUID,
        payload: McpServerPayload,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> McpServerResponse:
        """Apply a partial update to one of the user's MCP server rows."""
        row = await crud.update_mcp_server(
            session,
            user.id,
            server_id,
            name=payload.name,
            config=payload.config,
            status=payload.status,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="MCP server not found.")
        return _to_response(row)

    @router.delete("/{server_id}", status_code=204)
    async def delete_server(
        server_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Remove one MCP server row from the user's configuration."""
        removed = await crud.delete_mcp_server(session, user.id, server_id)
        if not removed:
            raise HTTPException(status_code=404, detail="MCP server not found.")

    return router
