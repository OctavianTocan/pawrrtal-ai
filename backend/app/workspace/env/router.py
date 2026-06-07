"""HTTP endpoints for per-workspace environment variables.

Workspace env files live at ``{workspace_root}/.env`` (encrypted at rest,
where ``workspace_root`` comes from the ``workspaces.path`` DB column) and
let users override gateway-level settings (e.g. their own ``GEMINI_API_KEY``)
without modifying the server's global ``.env``.  Each of a user's workspaces
has its own independent ``.env``.

Mounted at: ``/api/v1/workspaces/{workspace_id}/env``.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.infrastructure.keys import (
    OVERRIDABLE_KEYS,
    VALUE_FORBIDDEN_CHARS,
    load_workspace_env,
    save_workspace_env,
)
from app.models import Workspace
from app.plugins.env import plugin_overridable_env_keys
from app.plugins.errors import PluginError

logger = logging.getLogger(__name__)

# NOTE: Numeric limits on key count (was MAX_KEYS=10) and per-value length
# (was MAX_VALUE_LENGTH=512) were removed. The per-workspace .env is
# encrypted user-controlled data living inside the user's own workspace
# directory (0600 perms). The only hard security boundary that remains is
# the newline-rejection validator below (prevents key-injection on the
# line-based serializer). The allowlist still gates unknown keys with 400,
# but it now unions kernel-owned keys with env keys declared by plugins
# installed for the specific workspace.


class WorkspaceEnvVars(BaseModel):
    """Request body for ``PUT /api/v1/workspace/env``.

    Each entry in ``vars`` overrides the corresponding gateway-level setting.
    Empty-string values are persisted as "absent" (the encrypted file simply
    omits the key) so that clearing a field in the UI reverts to the
    gateway default.
    """

    vars: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of workspace env key names to their values. "
            "Unknown keys are rejected with 400. Values must not contain "
            "newline characters."
        ),
    )

    @field_validator("vars")
    @classmethod
    def _reject_newlines(cls, v: dict[str, str]) -> dict[str, str]:
        r"""Reject any value containing CR or LF.

        The on-disk format is one ``KEY=value`` per line, so a value
        containing a newline would split into a second key=value pair on
        the next read — letting a user with one writable key inject
        arbitrary other keys (e.g. ``GEMINI_API_KEY=...\nEXA_API_KEY=hijack``).
        Rejection at validation time is the only safe enforcement boundary
        because the serialiser does no escaping.
        """
        for key, value in v.items():
            if VALUE_FORBIDDEN_CHARS.search(value):
                raise ValueError(f"Value for '{key}' must not contain newline characters.")
        return v


class WorkspaceEnvResponse(BaseModel):
    """Response body for ``GET`` and ``PUT /api/v1/workspace/env``.

    Always contains every key users may configure in this workspace; keys
    the user has not set are returned with empty-string values so the
    frontend can render every input field without an extra schema fetch.
    """

    vars: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "All overridable workspace env keys. "
            "Keys not yet set by the user have an empty-string value."
        ),
    )


def _all_keys_response(
    env: dict[str, str],
    allowed_keys: frozenset[str],
) -> WorkspaceEnvResponse:
    """Project a stored env dict onto the canonical full-key response shape."""
    return WorkspaceEnvResponse(vars={k: env.get(k, "") for k in sorted(allowed_keys)})


def _allowed_workspace_env_keys(workspace_root: Path) -> frozenset[str]:
    """Return kernel and plugin env keys configurable for this workspace."""
    try:
        plugin_keys = plugin_overridable_env_keys(workspace_root=workspace_root)
    except PluginError as exc:
        logger.warning(
            "workspace_env: plugin env discovery failed for %s: %s",
            workspace_root,
            exc,
        )
        plugin_keys = frozenset()
    return OVERRIDABLE_KEYS | plugin_keys


async def _get_owned_workspace(
    workspace_id: uuid.UUID,
    user: User,
    session: AsyncSession,
) -> Workspace:
    """Return the workspace row after verifying it belongs to ``user``.

    Raises 404 (not 403) when the workspace exists but belongs to someone
    else — leaking ownership via the status code would let an attacker
    enumerate workspace IDs.
    """
    result = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == user.id,
        )
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


def get_workspace_env_router() -> APIRouter:
    """Build the per-workspace env override router.

    Three endpoints, all scoped to a single workspace owned by the caller:
      * ``GET  /workspaces/{workspace_id}/env`` — return the workspace's
        current overrides (with empty-string defaults for unset keys).
      * ``PUT  /workspaces/{workspace_id}/env`` — merge new overrides on
        top of existing ones. Empty-string values are stored as "absent"
        (the on-disk file omits them).
      * ``DELETE /workspaces/{workspace_id}/env/{key}`` — remove a single
        override, falling back to the gateway default for that key.

    All endpoints require the authenticated user to own the workspace.
    """
    router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-env"])

    @router.get("/{workspace_id}/env", response_model=WorkspaceEnvResponse)
    async def get_workspace_env(
        workspace_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspaceEnvResponse:
        """Return the workspace's env overrides."""
        ws = await _get_owned_workspace(workspace_id, user, session)
        workspace_root = Path(ws.path)
        allowed_keys = _allowed_workspace_env_keys(workspace_root)
        return _all_keys_response(load_workspace_env(workspace_root), allowed_keys)

    @router.put("/{workspace_id}/env", response_model=WorkspaceEnvResponse)
    async def put_workspace_env(
        workspace_id: uuid.UUID,
        payload: WorkspaceEnvVars,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspaceEnvResponse:
        """Merge ``payload.vars`` into the workspace's env file.

        Existing keys not mentioned in ``payload.vars`` are preserved
        (PATCH-like semantics, despite the PUT verb — the field-by-field
        UI never sends a full replace). Empty-string values are accepted
        and stored as "absent" so clearing a field in the UI reverts that
        key to the gateway default.
        """
        ws = await _get_owned_workspace(workspace_id, user, session)
        workspace_root = Path(ws.path)
        allowed_keys = _allowed_workspace_env_keys(workspace_root)
        for k in payload.vars:
            if k not in allowed_keys:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Unknown workspace env key: '{k}'. Allowed keys: {sorted(allowed_keys)}."
                    ),
                )
        existing = load_workspace_env(workspace_root)
        existing.update(payload.vars)
        save_workspace_env(workspace_root, existing)
        # Re-load from disk so the response reflects what was actually
        # persisted (empty-string values are stripped during save, so the
        # echoed payload should match what subsequent GETs return).
        return _all_keys_response(load_workspace_env(workspace_root), allowed_keys)

    @router.delete("/{workspace_id}/env/{key}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_workspace_env_key(
        workspace_id: uuid.UUID,
        key: str,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Remove a single override key for the workspace."""
        ws = await _get_owned_workspace(workspace_id, user, session)
        workspace_root = Path(ws.path)
        allowed_keys = _allowed_workspace_env_keys(workspace_root)
        if key not in allowed_keys:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown workspace env key: '{key}'.",
            )
        existing = load_workspace_env(workspace_root)
        existing.pop(key, None)
        save_workspace_env(workspace_root, existing)

    return router
