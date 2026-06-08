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

RUNTIME_GLOBAL_CAPABILITY_TYPES = frozenset({"channel"})
RUNTIME_GLOBAL_MANAGE_REASON = (
    "This plugin controls runtime-global channel adapters and is managed from "
    "global plugin state, not per-workspace settings."
)


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
    manageable: bool
    manage_reason: str | None
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
        _ensure_workspace_manageable(outcome)
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
        capability = _require_workspace_slot_capability(
            workspace_snapshot=snapshot,
            runtime_snapshot=_runtime_snapshot(),
            capability_key=payload.capability_key,
        )
        _ensure_capability_slot_manageable(capability)
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


def _runtime_snapshot() -> ContributionRegistrySnapshot:
    """Reload and return the runtime-global plugin snapshot."""
    _previous, current = get_plugin_host().reload()
    return current


def _response(
    *,
    workspace_id: uuid.UUID,
    snapshot: ContributionRegistrySnapshot,
) -> WorkspacePluginsResponse:
    """Serialize a plugin snapshot for HTTP clients."""
    runtime_snapshot = _runtime_snapshot()
    return WorkspacePluginsResponse(
        workspace_id=workspace_id,
        fingerprint=snapshot.fingerprint,
        plugins=[
            _plugin_read(
                outcome=outcome,
                snapshot=snapshot,
                runtime_snapshot=runtime_snapshot,
            )
            for outcome in snapshot.outcomes
        ],
    )


def _plugin_read(
    *,
    outcome: PluginLoadOutcome,
    snapshot: ContributionRegistrySnapshot,
    runtime_snapshot: ContributionRegistrySnapshot,
) -> PluginRead:
    """Serialize one plugin outcome."""
    effective_outcome, effective_snapshot = _effective_read_scope(
        outcome=outcome,
        workspace_snapshot=snapshot,
        runtime_snapshot=runtime_snapshot,
    )
    manageable = not _is_runtime_global_plugin(outcome)
    manage_reason = None if manageable else RUNTIME_GLOBAL_MANAGE_REASON
    manifest = effective_outcome.manifest
    return PluginRead(
        plugin_id=effective_outcome.plugin_id,
        name=manifest.name if manifest is not None else None,
        description=manifest.description if manifest is not None else None,
        version=manifest.version if manifest is not None else None,
        source_type=effective_outcome.source_type,
        status=effective_outcome.status,
        reason=effective_outcome.reason,
        enabled=effective_outcome.state.enabled,
        manageable=manageable,
        manage_reason=manage_reason,
        missing_env=list(effective_outcome.missing_env),
        fingerprint=effective_outcome.fingerprint,
        manifest_path=str(effective_outcome.manifest_path),
        capabilities=[
            _capability_read(capability=capability, snapshot=effective_snapshot)
            for capability in effective_snapshot.capabilities
            if capability.plugin_id == effective_outcome.plugin_id
        ],
    )


def _effective_read_scope(
    *,
    outcome: PluginLoadOutcome,
    workspace_snapshot: ContributionRegistrySnapshot,
    runtime_snapshot: ContributionRegistrySnapshot,
) -> tuple[PluginLoadOutcome, ContributionRegistrySnapshot]:
    """Return the state scope that should be shown for one plugin."""
    if not _is_runtime_global_plugin(outcome):
        return outcome, workspace_snapshot
    runtime_outcome = runtime_snapshot.outcome_for(outcome.plugin_id)
    if runtime_outcome is None:
        return outcome, workspace_snapshot
    return runtime_outcome, runtime_snapshot


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


def _find_capability(
    *,
    snapshot: ContributionRegistrySnapshot,
    capability_key: str,
) -> CapabilityRecord | None:
    """Return a capability by composite key when the snapshot contains it."""
    for capability in snapshot.capabilities:
        if capability.key == capability_key:
            return capability
    return None


def _require_workspace_slot_capability(
    *,
    workspace_snapshot: ContributionRegistrySnapshot,
    runtime_snapshot: ContributionRegistrySnapshot,
    capability_key: str,
) -> CapabilityRecord:
    """Return a workspace capability or reject runtime-global slot writes."""
    capability = _find_capability(snapshot=workspace_snapshot, capability_key=capability_key)
    if capability is not None:
        return capability
    runtime_capability = _find_capability(snapshot=runtime_snapshot, capability_key=capability_key)
    if runtime_capability is not None:
        _ensure_capability_slot_manageable(runtime_capability)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Capability {capability_key!r} is not installed.",
    )


def _ensure_workspace_manageable(outcome: PluginLoadOutcome) -> None:
    """Reject workspace writes for plugins managed by runtime-global state."""
    if _is_runtime_global_plugin(outcome):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=RUNTIME_GLOBAL_MANAGE_REASON,
        )


def _ensure_capability_slot_manageable(capability: CapabilityRecord) -> None:
    """Reject workspace slot preferences for runtime-global capabilities."""
    if capability.type in RUNTIME_GLOBAL_CAPABILITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=RUNTIME_GLOBAL_MANAGE_REASON,
        )


def _is_runtime_global_plugin(outcome: PluginLoadOutcome) -> bool:
    """Return whether a plugin's capabilities are managed outside workspaces."""
    manifest = outcome.manifest
    if manifest is None:
        return False
    return any(
        capability.type in RUNTIME_GLOBAL_CAPABILITY_TYPES for capability in manifest.capabilities
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
