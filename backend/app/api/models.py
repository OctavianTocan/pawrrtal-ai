"""``/api/v1/models`` — exposes the backend catalog to clients."""

from __future__ import annotations

from fastapi import Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from pydantic import BaseModel

from app.core.providers.catalog import CATALOG_ETAG, MODEL_CATALOG, ModelEntry
from app.core.providers.factory import host_authenticated
from app.core.providers.model_id import Host
from app.db import User
from app.users import get_allowed_user


def _auth_fingerprint() -> str:
    """Stable per-process fingerprint of which hosts are authenticated.

    Folded into the ETag so a deployment that authenticates an extra
    provider after boot (or unsets a key) produces a different ETag
    and clients re-fetch instead of replaying a stale 304. Stable
    ordering means the same auth state always produces the same
    fingerprint string.
    """
    return "".join(
        "1" if host_authenticated(h) else "0" for h in sorted(Host, key=lambda h: h.value)
    )


# RFC 7232 requires ``ETag`` values to be wrapped in double quotes.  The
# ``CATALOG_ETAG`` constant is a bare 16-hex string; we quote it once here
# so both the response header and the ``If-None-Match`` comparison agree.
# The auth fingerprint is appended so the ``304`` path doesn't replay a
# stale list when the deployment's authenticated provider set changes
# (issue #370).
ETAG_HEADER = f'"{CATALOG_ETAG}-{_auth_fingerprint()}"'


class ModelOption(BaseModel):
    """One model returned by ``GET /api/v1/models``."""

    id: str
    host: str
    vendor: str
    model: str
    display_name: str
    short_name: str
    description: str
    is_default: bool


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
        is_default=entry.is_default,
    )


def get_models_router() -> APIRouter:
    """Build the ``/api/v1/models`` router.

    Returns:
        An ``APIRouter`` exposing ``GET /api/v1/models`` behind the
        standard authed-user dependency.
    """
    router = APIRouter(prefix="/api/v1/models", tags=["models"])

    @router.get("")
    def list_models(
        request: Request,
        _user: User = Depends(get_allowed_user),
    ) -> Response:
        """Return the catalog with ``ETag`` caching.

        A ``304 Not Modified`` (empty body) is returned when the
        client's ``If-None-Match`` matches the in-memory catalog
        hash. Use ``Response(status_code=304)`` rather than
        ``HTTPException(304)`` so the response has no body — FastAPI
        serialises ``HTTPException`` with a ``detail`` payload,
        which violates RFC 7232.
        """
        if request.headers.get("if-none-match") == ETAG_HEADER:
            return Response(
                status_code=status.HTTP_304_NOT_MODIFIED,
                headers={"ETag": ETAG_HEADER},
            )
        # Filter out catalog entries whose host doesn't have credentials
        # (or, for ``gemini_cli``, doesn't have the binary on PATH). Users
        # shouldn't see picker rows they can't actually click — issue #370.
        authed_entries = [e for e in MODEL_CATALOG if host_authenticated(e.host)]
        body = ModelsResponse(models=[_to_option(e) for e in authed_entries])
        return JSONResponse(
            content=body.model_dump(),
            headers={
                "ETag": ETAG_HEADER,
                "Cache-Control": "private, must-revalidate",
            },
        )

    return router
