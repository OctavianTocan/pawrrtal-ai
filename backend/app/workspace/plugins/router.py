"""HTTP endpoints for workspace plugin management."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.models import Workspace
from app.plugins.capability_catalog import CapabilityRecord
from app.plugins.host import get_plugin_host
from app.plugins.registry import ContributionRegistrySnapshot, PluginLoadOutcome
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state


class PluginUpdateRequest(BaseModel):
    """Request body for enabling or disabling one workspace plugin."""

    enabled: bool = Field(description="Whether the plugin should contribute capabilities.")


class SlotPreferenceRequest(BaseModel):
    """Request body for setting one preferred capability for a slot."""

    capability_key: str = Field(description="Composite key shaped as plugin_id/capability_id.")


class PluginCapabilityRead(BaseModel):
    """One plugin capability row returned to the frontend."""

    plugin_id: str
    capability_id: str
    key: str
    type: str
    title: str
    description: str
    tags: list[str]
    intents: list[str]
    slots: list[str]
    state: str
    preferred: bool
    priority: int
    exposure: str
    permissions: list[str]
    requires_confirmation: bool
    input_schema: dict[str, object]
    examples: list[dict[str, object]]
    invokable: bool


class PluginRead(BaseModel):
    """One plugin load outcome with manifest metadata and capabilities."""

    plugin_id: str
    name: str | None
    description: str | None
    version: str | None
    source_type: str
    status: str
    reason: str | None
    enabled: bool
    missing_env: list[str]
    fingerprint: str | None
    manifest_path: str
    capabilities: list[PluginCapabilityRead]


class WorkspacePluginsResponse(BaseModel):
    """Workspace plugin snapshot returned by the management API."""

    workspace_id: uuid.UUID
    fingerprint: str
    plugins: list[PluginRead]


async def _get_owned_workspace(
    workspace_id: uuid.UUID,
    user: User,
    session: AsyncSession,
) -> Workspace:
    """Return a workspace after verifying it belongs to the authenticated user."""
    result = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == user.id,
        )
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


def get_workspace_plugins_router() -> APIRouter:
    """Build the workspace plugin management router."""
    router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-plugins"])

    @router.get("/{workspace_id}/plugins", response_model=WorkspacePluginsResponse)
    async def list_workspace_plugins(
        workspace_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspacePluginsResponse:
        """Return plugin load state and capabilities for one workspace."""
        workspace = await _get_owned_workspace(workspace_id, user, session)
        snapshot = _snapshot(Path(workspace.path))
        return _response(workspace_id=workspace.id, snapshot=snapshot)

    @router.patch("/{workspace_id}/plugins/{plugin_id}", response_model=WorkspacePluginsResponse)
    async def update_workspace_plugin(
        workspace_id: uuid.UUID,
        plugin_id: str,
        payload: PluginUpdateRequest,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspacePluginsResponse:
        """Enable or disable one plugin for a workspace."""
        workspace = await _get_owned_workspace(workspace_id, user, session)
        workspace_root = Path(workspace.path)
        snapshot = _snapshot(workspace_root)
        outcome = _require_outcome(snapshot=snapshot, plugin_id=plugin_id)
        _save_state(
            workspace_root=workspace_root,
            plugin_id=plugin_id,
            state=outcome.state,
            enabled=payload.enabled,
        )
        return _response(workspace_id=workspace.id, snapshot=_snapshot(workspace_root))

    @router.put(
        "/{workspace_id}/plugins/slots/{slot_id}",
        response_model=WorkspacePluginsResponse,
    )
    async def prefer_workspace_plugin_slot(
        workspace_id: uuid.UUID,
        slot_id: str,
        payload: SlotPreferenceRequest,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspacePluginsResponse:
        """Set one preferred capability for a workspace slot."""
        workspace = await _get_owned_workspace(workspace_id, user, session)
        workspace_root = Path(workspace.path)
        snapshot = _snapshot(workspace_root)
        capability = _require_capability(snapshot=snapshot, capability_key=payload.capability_key)
        if slot_id not in capability.slots:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Capability {payload.capability_key!r} does not fit slot {slot_id!r}.",
            )
        outcome = _require_outcome(snapshot=snapshot, plugin_id=capability.plugin_id)
        _save_slot_preference(
            workspace_root=workspace_root,
            plugin_id=capability.plugin_id,
            state=outcome.state,
            slot_id=slot_id,
            capability_key=payload.capability_key,
        )
        return _response(workspace_id=workspace.id, snapshot=_snapshot(workspace_root))

    return router


def _snapshot(workspace_root: Path) -> ContributionRegistrySnapshot:
    """Reload and return the current plugin snapshot for a workspace."""
    _previous, current = get_plugin_host().reload(workspace_root=workspace_root)
    return current


def _response(
    *,
    workspace_id: uuid.UUID,
    snapshot: ContributionRegistrySnapshot,
) -> WorkspacePluginsResponse:
    """Serialize a plugin snapshot for HTTP clients."""
    return WorkspacePluginsResponse(
        workspace_id=workspace_id,
        fingerprint=snapshot.fingerprint,
        plugins=[_plugin_read(outcome=outcome, snapshot=snapshot) for outcome in snapshot.outcomes],
    )


def _plugin_read(
    *,
    outcome: PluginLoadOutcome,
    snapshot: ContributionRegistrySnapshot,
) -> PluginRead:
    """Serialize one plugin outcome."""
    manifest = outcome.manifest
    return PluginRead(
        plugin_id=outcome.plugin_id,
        name=manifest.name if manifest is not None else None,
        description=manifest.description if manifest is not None else None,
        version=manifest.version if manifest is not None else None,
        source_type=outcome.source_type,
        status=outcome.status,
        reason=outcome.reason,
        enabled=outcome.state.enabled,
        missing_env=list(outcome.missing_env),
        fingerprint=outcome.fingerprint,
        manifest_path=str(outcome.manifest_path),
        capabilities=[
            _capability_read(capability=capability, snapshot=snapshot)
            for capability in snapshot.capabilities
            if capability.plugin_id == outcome.plugin_id
        ],
    )


def _capability_read(
    *,
    capability: CapabilityRecord,
    snapshot: ContributionRegistrySnapshot,
) -> PluginCapabilityRead:
    """Serialize one capability row."""
    payload = capability.to_wire(preferred=_is_preferred(snapshot=snapshot, capability=capability))
    return PluginCapabilityRead.model_validate(payload)


def _is_preferred(
    *,
    snapshot: ContributionRegistrySnapshot,
    capability: CapabilityRecord,
) -> bool:
    """Return whether the capability is preferred for any declared slot."""
    for slot in capability.slots:
        if capability.key in _slot_preferences(snapshot=snapshot, slot_id=slot):
            return True
    return False


def _slot_preferences(
    *,
    snapshot: ContributionRegistrySnapshot,
    slot_id: str,
) -> tuple[str, ...]:
    """Collect ordered slot preferences from plugin state."""
    preferences: list[str] = []
    for outcome in snapshot.outcomes:
        preferences.extend(outcome.state.slot_preference_keys(slot_id))
    return tuple(dict.fromkeys(preferences))


def _require_outcome(
    *,
    snapshot: ContributionRegistrySnapshot,
    plugin_id: str,
) -> PluginLoadOutcome:
    """Return a plugin outcome or raise 404."""
    outcome = snapshot.outcome_for(plugin_id)
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin {plugin_id!r} is not installed.",
        )
    return outcome


def _require_capability(
    *,
    snapshot: ContributionRegistrySnapshot,
    capability_key: str,
) -> CapabilityRecord:
    """Return a capability by composite key or raise 404."""
    for capability in snapshot.capabilities:
        if capability.key == capability_key:
            return capability
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Capability {capability_key!r} is not installed.",
    )


def _save_state(
    *,
    workspace_root: Path,
    plugin_id: str,
    state: PluginState,
    enabled: bool,
) -> None:
    """Persist plugin enablement while preserving the rest of its state."""
    save_plugin_state(
        plugin_state_path(
            plugin_id=plugin_id,
            scope="workspace",
            workspace_root=workspace_root,
        ),
        PluginState(
            enabled=enabled,
            capabilities=state.capabilities,
            slot_preferences=state.slot_preferences,
            validated_fingerprint=state.validated_fingerprint,
            validated_at=state.validated_at,
            last_validation=state.last_validation,
            failure_reason=state.failure_reason,
            doctor=state.doctor,
        ),
    )


def _save_slot_preference(
    *,
    workspace_root: Path,
    plugin_id: str,
    state: PluginState,
    slot_id: str,
    capability_key: str,
) -> None:
    """Persist a single slot preference while preserving plugin enablement."""
    preferences = dict(state.slot_preferences)
    preferences[slot_id] = (capability_key,)
    save_plugin_state(
        plugin_state_path(
            plugin_id=plugin_id,
            scope="workspace",
            workspace_root=workspace_root,
        ),
        PluginState(
            enabled=state.enabled,
            capabilities=state.capabilities,
            slot_preferences=preferences,
            validated_fingerprint=state.validated_fingerprint,
            validated_at=state.validated_at,
            last_validation=state.last_validation,
            failure_reason=state.failure_reason,
            doctor=state.doctor,
        ),
    )
