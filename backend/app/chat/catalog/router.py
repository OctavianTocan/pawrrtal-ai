"""``/api/v1/models`` — exposes the backend catalog to clients."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.providers.catalog import CATALOG_ETAG, MODEL_CATALOG, ModelEntry
from app.providers.factory import host_authenticated
from app.providers.model_id import Host
from app.providers.plugin_provider import PluginModelEntry, provider_model_entries
from app.workspace.crud import get_default_workspace


def _auth_fingerprint(workspace_root: Path | None) -> str:
    """Fingerprint of which hosts are authenticated for this request.

    Folded into the ETag so a deployment that authenticates an extra
    provider after boot (or unsets a key, or installs the gemini
    binary on PATH) produces a different ETag and clients re-fetch
    instead of replaying a stale 304. Stable ordering means the same
    auth state always produces the same fingerprint string.

    Workspace-keyed deployments (the documented per-user .env path)
    produce a workspace-specific fingerprint when ``workspace_root``
    is set, so two users with different workspace credentials get
    distinct ETags and won't share cached responses.
    """
    return "".join(
        "1" if host_authenticated(h, workspace_root=workspace_root) else "0"
        for h in sorted(Host, key=lambda h: h.value)
    )


def _etag_for(workspace_root: Path | None) -> str:
    """Build the per-request ETag header value.

    Computed live (not cached at module scope) because the auth state
    can change during process lifetime — a new key written to a
    workspace ``.env``, the ``gemini`` binary appearing on PATH, etc.
    A stale module-level ETag would cause ``If-None-Match`` to return
    304 with the old filtered list (issue #370 review feedback).
    """
    return f'"{CATALOG_ETAG}-{_auth_fingerprint(workspace_root)}-{_plugin_fingerprint(workspace_root)}"'


class ModelOption(BaseModel):
    """One model returned by ``GET /api/v1/models``."""

    id: str
    host: str
    vendor: str
    model: str
    display_name: str
    short_name: str
    description: str


class ModelsResponse(BaseModel):
    """Envelope for the catalog response."""

    models: list[ModelOption]


def _to_option(entry: ModelEntry) -> ModelOption:
    return ModelOption(
        id=entry.id,
        host=entry.host.value,
        vendor=entry.vendor.value,
        model=entry.model,
        display_name=entry.display_name,
        short_name=entry.short_name,
        description=entry.description,
    )


def _plugin_to_option(entry: PluginModelEntry) -> ModelOption:
    return ModelOption(
        id=entry.id,
        host=entry.parsed.host,
        vendor=entry.parsed.vendor,
        model=entry.parsed.model,
        display_name=entry.display_name,
        short_name=entry.short_name,
        description=entry.description,
    )


def get_models_router() -> APIRouter:
    """Build the ``/api/v1/models`` router.

    Returns:
        An ``APIRouter`` exposing ``GET /api/v1/models`` behind the
        standard authed-user dependency.
    """
    router = APIRouter(prefix="/api/v1/models", tags=["models"])

    @router.get("")
    async def list_models(
        request: Request,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> Response:
        """Return the catalog with ``ETag`` caching, filtered by auth.

        The user's default workspace (if any) is resolved so the
        filter sees per-workspace credential overrides — the
        documented path for production deployments where keys live
        in the workspace ``.env`` rather than the gateway-global
        environment. The ETag is computed per-request so live changes
        to auth state (new workspace key, ``gemini`` binary appearing
        on PATH) don't get masked by a stale 304.

        A ``304 Not Modified`` (empty body) is returned when the
        client's ``If-None-Match`` matches. ``Response(status_code=304)``
        keeps the body empty per RFC 7232 (``HTTPException(304)`` would
        serialise a ``detail`` payload, which the spec forbids).
        """
        workspace = await get_default_workspace(user.id, session)
        workspace_root = Path(workspace.path) if workspace is not None else None
        etag = _etag_for(workspace_root)
        if request.headers.get("if-none-match") == etag:
            return Response(
                status_code=status.HTTP_304_NOT_MODIFIED,
                headers={"ETag": etag},
            )
        # Filter out catalog entries whose host doesn't have credentials
        # (or, for ``gemini_cli``, doesn't have the binary on PATH). Users
        # shouldn't see picker rows they can't actually click — issue #370.
        authed_entries = [
            e for e in MODEL_CATALOG if host_authenticated(e.host, workspace_root=workspace_root)
        ]
        plugin_entries = provider_model_entries(workspace_root=workspace_root)
        body = ModelsResponse(
            models=[
                *[_to_option(e) for e in authed_entries],
                *[_plugin_to_option(e) for e in plugin_entries],
            ]
        )
        return JSONResponse(
            content=body.model_dump(),
            headers={
                "ETag": etag,
                "Cache-Control": "private, must-revalidate",
            },
        )

    return router


def _plugin_fingerprint(workspace_root: Path | None) -> str:
    """Return a stable fingerprint for active provider plugin models."""
    entries = provider_model_entries(workspace_root=workspace_root)
    payload = json.dumps([entry.id for entry in entries], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
