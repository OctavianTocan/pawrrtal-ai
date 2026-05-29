"""HTTP endpoints for workspace management.

Workspaces are OpenClaw-style agent home directories.  Each user can own
multiple workspaces; the frontend shows the file tree and lets users read,
write, and delete files inside their workspace.

Agents access the filesystem directly via tools — these endpoints exist
purely to surface workspace data in the UI.

Mounted at: /api/v1/workspaces
"""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tools.skills import read_skill_manifest
from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.models import Workspace
from app.schemas import (
    OnboardingStatus,
    SkillRead,
    WorkspaceCreate,
    WorkspaceFileContent,
    WorkspaceFileNode,
    WorkspaceFileWrite,
    WorkspaceRead,
    WorkspaceTreeResponse,
    WorkspaceUpdate,
)
from app.workspace.crud import (
    create_workspace,
    delete_workspace,
    get_default_workspace,
    list_workspaces,
    update_workspace,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_owned_workspace(
    workspace_id: uuid.UUID,
    user: User,
    session: AsyncSession,
) -> Workspace:
    """Fetch a workspace by ID and verify it belongs to the authenticated user."""
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


def _safe_child(root: Path, relative: str, *, follow_final_symlink: bool = True) -> Path:
    """Resolve a workspace-relative path and verify it stays inside the root.

    Raises 400 if the path escapes the workspace root (directory traversal).
    """
    candidate = root / relative
    resolved = candidate.resolve() if follow_final_symlink else candidate.parent.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be inside the workspace",
        ) from exc
    return resolved if follow_final_symlink else candidate


def _has_symlink_parent(root: Path, relative: str) -> bool:
    """Return True when any parent component in ``relative`` is a symlink."""
    current = root
    parts = Path(relative).parts[:-1]
    for part in parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _build_tree(root: Path, relative_root: Path | None = None) -> list[WorkspaceFileNode]:
    """Recursively build a flat list of file-tree nodes.

    ``relative_root`` is the workspace root used to compute workspace-relative
    paths; it defaults to ``root`` on the first call.
    """
    if relative_root is None:
        relative_root = root

    nodes: list[WorkspaceFileNode] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return nodes

    for entry in entries:
        rel = entry.relative_to(relative_root).as_posix()
        if entry.is_dir():
            nodes.append(WorkspaceFileNode(name=entry.name, path=rel, is_dir=True))
            nodes.extend(_build_tree(entry, relative_root))
        else:
            nodes.append(
                WorkspaceFileNode(
                    name=entry.name,
                    path=rel,
                    is_dir=False,
                    size=entry.stat().st_size,
                )
            )
    return nodes


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def get_workspace_router() -> APIRouter:
    """Build the workspace router (mounted at /api/v1/workspaces)."""
    router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])
    _register_listing_routes(router)
    _register_crud_routes(router)
    _register_tree_route(router)
    _register_file_routes(router)
    _register_skills_route(router)
    _register_serve_route(router)
    return router


def _validate_workspace_path(raw_path: str) -> str:
    """Return a normalised workspace path or raise 400 if it's unsafe.

    Workspace paths must (a) be absolute and (b) live inside the configured
    ``workspace_base_dir`` — otherwise a client could point a workspace at
    arbitrary filesystem locations and trick later file-tree / read / write
    endpoints into operating outside the sandbox.
    """
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace path must be absolute",
        )
    base = Path(settings.workspace_base_dir).resolve()
    try:
        candidate.resolve().relative_to(base)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workspace path must live under {base}",
        ) from exc
    return str(candidate)


def _register_crud_routes(router: APIRouter) -> None:
    """Register POST / PATCH / DELETE workspace endpoints.

    Workspaces were historically created only as a side-effect of
    ``PUT /api/v1/personalization`` (via ``ensure_default_workspace``).
    These routes expose the same machinery directly so external clients —
    paw, future SDKs, scripts — can manage workspaces without going
    through onboarding.
    """

    @router.post(
        "",
        response_model=WorkspaceRead,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_user_workspace(
        payload: WorkspaceCreate,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspaceRead:
        """Create a new workspace for the authenticated user.

        When ``payload.is_default`` is True any existing default workspace
        is demoted first so the partial unique index stays satisfied.
        Duplicate names return 409 (we surface a clear error rather than
        creating two visually identical entries the user can't distinguish).
        """
        existing = await list_workspaces(user.id, session)
        if any(ws.name == payload.name for ws in existing):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workspace named {payload.name!r} already exists",
            )

        seed_path = Path(_validate_workspace_path(payload.path)) if payload.path else None
        slug = payload.slug or "main"
        is_default = payload.is_default or len(existing) == 0
        if is_default:
            current_default = await get_default_workspace(user.id, session)
            if current_default is not None:
                current_default.is_default = False
                await session.flush()

        workspace = await create_workspace(
            user_id=user.id,
            session=session,
            name=payload.name,
            slug=slug,
            is_default=is_default,
            path=seed_path,
        )
        await session.commit()
        await session.refresh(workspace)
        return WorkspaceRead.model_validate(workspace)

    @router.patch("/{workspace_id}", response_model=WorkspaceRead)
    async def patch_user_workspace(
        workspace_id: uuid.UUID,
        payload: WorkspaceUpdate,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspaceRead:
        """Update a workspace's name, slug, path, or default flag."""
        workspace = await _get_owned_workspace(workspace_id, user, session)
        validated_path = (
            _validate_workspace_path(payload.path) if payload.path is not None else None
        )
        await update_workspace(
            session,
            workspace,
            name=payload.name,
            slug=payload.slug,
            path=validated_path,
            is_default=payload.is_default,
        )
        await session.commit()
        await session.refresh(workspace)
        return WorkspaceRead.model_validate(workspace)

    @router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_user_workspace(
        workspace_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Delete a workspace.

        Refuses with 409 when the workspace is the user's last one or is
        currently marked default — the chat router requires a default
        workspace to run, so silently deleting it would break the user's
        ability to chat without a clear failure mode.
        """
        workspace = await _get_owned_workspace(workspace_id, user, session)
        existing = await list_workspaces(user.id, session)
        if len(existing) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete the user's only workspace",
            )
        if workspace.is_default:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete the default workspace. Promote another workspace first.",
            )
        await delete_workspace(session, workspace)
        await session.commit()


def _register_listing_routes(router: APIRouter) -> None:
    """Register the workspace listing + onboarding-status endpoints."""

    @router.get("", response_model=list[WorkspaceRead])
    async def list_user_workspaces(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> list[WorkspaceRead]:
        """Return all workspaces owned by the authenticated user."""
        workspaces = await list_workspaces(user.id, session)
        return [WorkspaceRead.model_validate(ws) for ws in workspaces]

    @router.get("/onboarding-status", response_model=OnboardingStatus)
    async def get_onboarding_status(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> OnboardingStatus:
        """Return whether the user has a default workspace ready."""
        workspace = await get_default_workspace(user.id, session)
        return OnboardingStatus(
            has_workspace_ready=workspace is not None,
            workspace=WorkspaceRead.model_validate(workspace) if workspace else None,
        )


def _register_tree_route(router: APIRouter) -> None:
    """Register the workspace file-tree endpoint."""

    @router.get("/{workspace_id}/tree", response_model=WorkspaceTreeResponse)
    async def get_workspace_tree(
        workspace_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspaceTreeResponse:
        """Return the full file tree of a workspace as a flat node list."""
        ws = await _get_owned_workspace(workspace_id, user, session)
        root = Path(ws.path)
        if not await anyio.Path(root).exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace directory not found on disk",
            )
        return WorkspaceTreeResponse(
            workspace_id=ws.id,
            nodes=_build_tree(root),
        )


def _register_file_routes(router: APIRouter) -> None:
    """Register the per-file read/write/delete endpoints."""

    @router.get("/{workspace_id}/files/{file_path:path}", response_model=WorkspaceFileContent)
    async def read_workspace_file(
        workspace_id: uuid.UUID,
        file_path: str,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspaceFileContent:
        """Read a file's text content from the workspace."""
        ws = await _get_owned_workspace(workspace_id, user, session)
        target = _safe_child(Path(ws.path), file_path)

        if not target.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if target.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path is a directory, not a file",
            )

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File is not valid UTF-8 text",
            ) from exc

        return WorkspaceFileContent(path=file_path, content=content)

    @router.put(
        "/{workspace_id}/files/{file_path:path}",
        response_model=WorkspaceFileContent,
        status_code=status.HTTP_200_OK,
    )
    async def write_workspace_file(
        workspace_id: uuid.UUID,
        file_path: str,
        payload: WorkspaceFileWrite,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> WorkspaceFileContent:
        """Create or replace a text file inside the workspace."""
        ws = await _get_owned_workspace(workspace_id, user, session)
        target = _safe_child(Path(ws.path), file_path, follow_final_symlink=False)

        if _has_symlink_parent(Path(ws.path), file_path) or target.is_symlink():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot write through a workspace symlink",
            )
        if target.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path resolves to a directory",
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload.content, encoding="utf-8")

        return WorkspaceFileContent(path=file_path, content=payload.content)

    @router.delete(
        "/{workspace_id}/files/{file_path:path}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_workspace_file(
        workspace_id: uuid.UUID,
        file_path: str,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Delete a file from the workspace.  Does not delete directories."""
        ws = await _get_owned_workspace(workspace_id, user, session)
        target = _safe_child(Path(ws.path), file_path, follow_final_symlink=False)

        if _has_symlink_parent(Path(ws.path), file_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete through a workspace symlink",
            )
        if not target.exists() and not target.is_symlink():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if target.is_dir() and not target.is_symlink():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use a dedicated endpoint to delete directories",
            )

        target.unlink()


def _register_skills_route(router: APIRouter) -> None:
    """Register the workspace skill listing endpoint."""

    @router.get("/{workspace_id}/skills", response_model=list[SkillRead])
    async def list_workspace_skills(
        workspace_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> list[SkillRead]:
        """Return the skill list for a workspace.

        Reads ``.agent/skills/_manifest.jsonl`` and falls back to
        directory discovery. Returns an empty list (not 404) when the
        workspace has no skills yet.
        """
        ws = await _get_owned_workspace(workspace_id, user, session)
        root = Path(ws.path)
        if not await anyio.Path(root).exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace directory not found on disk",
            )
        entries = read_skill_manifest(root)
        return [
            SkillRead(
                name=e.name,
                trigger=e.trigger,
                summary=e.summary,
                has_skill_md=e.has_skill_md,
            )
            for e in entries
        ]


def _register_serve_route(router: APIRouter) -> None:
    """Register the default-workspace binary file serving endpoint."""

    @router.get(
        "/default/serve/{file_path:path}",
        response_class=FileResponse,
        summary="Serve a binary file from the user's default workspace",
    )
    async def serve_default_workspace_file(
        file_path: str,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> FileResponse:
        """Serve a file from the user's default workspace with its detected MIME type.

        Unlike the text-only ``GET /{workspace_id}/files/{file_path}`` endpoint,
        this route returns raw bytes (``FileResponse``) so the frontend can render
        images, audio, and other binary artifacts that agents produce via the
        ``send_message`` tool.

        Path traversal is blocked: the resolved target must stay inside the
        workspace root or the request is rejected with 400.

        Args:
            file_path: Workspace-relative path (e.g. ``artifacts/chart.png``).
            user: Authenticated user (injected by FastAPI).
            session: Database session (injected by FastAPI).

        Returns:
            The file streamed with the appropriate ``Content-Type`` header.
        """
        ws = await get_default_workspace(user.id, session)
        if ws is None:
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail="No default workspace found.  Complete onboarding first.",
            )

        root = await anyio.to_thread.run_sync(Path(ws.path).resolve)
        target = _safe_child(root, file_path)

        if not target.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if target.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path is a directory, not a file",
            )

        mime, _ = mimetypes.guess_type(str(target))
        return FileResponse(
            path=str(target),
            media_type=mime or "application/octet-stream",
            filename=target.name,
        )
