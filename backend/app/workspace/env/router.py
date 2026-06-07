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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
from app.plugins.contributions import EnvVarSpec
from app.plugins.env import plugin_env_specs_for_workspace
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


class WorkspaceEnvKeyRead(BaseModel):
    """Display metadata for one workspace-configurable env key."""

    key: str
    label: str
    description: str
    secret: bool
    required: bool
    source: Literal["kernel", "plugin"]
    help_url: str | None = None


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
    keys: list[WorkspaceEnvKeyRead] = Field(
        default_factory=list,
        description="Display metadata for every key in vars.",
    )


@dataclass(frozen=True, slots=True)
class WorkspaceEnvSchema:
    """Allowlist and metadata for one workspace env surface."""

    allowed_keys: frozenset[str]
    keys: tuple[WorkspaceEnvKeyRead, ...]


def _all_keys_response(env: dict[str, str], schema: WorkspaceEnvSchema) -> WorkspaceEnvResponse:
    """Project a stored env dict onto the canonical full-key response shape."""
    return WorkspaceEnvResponse(
        vars={k: env.get(k, "") for k in sorted(schema.allowed_keys)},
        keys=list(schema.keys),
    )


def _workspace_env_schema(workspace_root: Path) -> WorkspaceEnvSchema:
    """Return configurable env keys plus display metadata for this workspace."""
    try:
        plugin_specs = plugin_env_specs_for_workspace(workspace_root=workspace_root)
    except PluginError as exc:
        logger.warning(
            "workspace_env: plugin env discovery failed for %s: %s",
            workspace_root,
            exc,
        )
        plugin_specs = ()
    plugin_spec_by_name = {spec.name: spec for spec in plugin_specs}
    allowed_keys = OVERRIDABLE_KEYS | frozenset(plugin_spec_by_name)
    return WorkspaceEnvSchema(
        allowed_keys=allowed_keys,
        keys=tuple(
            _key_metadata(key=key, plugin_spec=plugin_spec_by_name.get(key))
            for key in sorted(allowed_keys)
        ),
    )


def _key_metadata(
    *,
    key: str,
    plugin_spec: EnvVarSpec | None,
) -> WorkspaceEnvKeyRead:
    """Return display metadata for a kernel or plugin env key."""
    if plugin_spec is not None and key not in OVERRIDABLE_KEYS:
        return WorkspaceEnvKeyRead(
            key=key,
            label=plugin_spec.label,
            description=plugin_spec.description or f"Workspace value for {plugin_spec.label}.",
            secret=plugin_spec.secret,
            required=plugin_spec.required,
            source="plugin",
            help_url=plugin_spec.help_url,
        )
    return WorkspaceEnvKeyRead(
        key=key,
        label=_label_from_env_key(key),
        description=f"Workspace override for {key}.",
        secret=_is_secret_kernel_key(key),
        required=False,
        source="kernel",
    )


def _label_from_env_key(key: str) -> str:
    """Return a readable fallback label for an env key."""
    return key.replace("_", " ").title()


def _is_secret_kernel_key(key: str) -> bool:
    """Return whether the built-in workspace env key should be masked."""
    return not (key == "GITHUB_ISSUES_REPO" or key.startswith("ACTIVE_RECALL_"))


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
        schema = _workspace_env_schema(workspace_root)
        return _all_keys_response(load_workspace_env(workspace_root), schema)

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
        schema = _workspace_env_schema(workspace_root)
        for k in payload.vars:
            if k not in schema.allowed_keys:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Unknown workspace env key: '{k}'. "
                        f"Allowed keys: {sorted(schema.allowed_keys)}."
                    ),
                )
        existing = load_workspace_env(workspace_root)
        existing.update(payload.vars)
        save_workspace_env(workspace_root, existing)
        # Re-load from disk so the response reflects what was actually
        # persisted (empty-string values are stripped during save, so the
        # echoed payload should match what subsequent GETs return).
        return _all_keys_response(load_workspace_env(workspace_root), schema)

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
        schema = _workspace_env_schema(workspace_root)
        if key not in schema.allowed_keys:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown workspace env key: '{key}'.",
            )
        existing = load_workspace_env(workspace_root)
        existing.pop(key, None)
        save_workspace_env(workspace_root, existing)

    return router
