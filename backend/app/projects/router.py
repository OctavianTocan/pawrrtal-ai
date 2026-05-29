"""HTTP endpoints for project management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.models import Project
from app.projects import crud
from app.schemas import ProjectCreate, ProjectRead, ProjectUpdate


def _serialize(project: Project) -> ProjectRead:
    """Build a {@link ProjectRead} from a Project ORM row."""
    return ProjectRead(
        id=project.id,
        user_id=project.user_id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def get_projects_router() -> APIRouter:
    """Build the projects router."""
    router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

    @router.get("", response_model=list[ProjectRead])
    async def list_projects(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> list[ProjectRead]:
        """List every project owned by the authenticated user."""
        projects = await crud.list_projects(user.id, session)
        return [_serialize(project) for project in projects]

    @router.post("", response_model=ProjectRead, status_code=201)
    async def create_project(
        payload: ProjectCreate,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> ProjectRead:
        """Create a new project owned by the authenticated user."""
        project = await crud.create_project(user.id, session, payload)
        return _serialize(project)

    @router.patch("/{project_id}", response_model=ProjectRead)
    async def update_project(
        project_id: uuid.UUID,
        payload: ProjectUpdate,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> ProjectRead:
        """Rename a project (currently the only mutable field)."""
        project = await crud.update_project(
            payload=payload,
            user_id=user.id,
            project_id=project_id,
            session=session,
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return _serialize(project)

    @router.delete("/{project_id}", status_code=204)
    async def delete_project(
        project_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Delete a project. Linked conversations are unlinked, not deleted."""
        deleted = await crud.delete_project(user.id, session, project_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Project not found")

    return router
