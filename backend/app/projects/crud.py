"""CRUD operations for the Project model.

All functions enforce user ownership — a user can only access or modify
their own projects.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.models import Project
from app.schemas import ProjectCreate, ProjectUpdate


async def create_project(
    user_id: uuid.UUID, session: AsyncSession, payload: ProjectCreate
) -> Project:
    """Create a new project owned by the given user.

    Args:
        user_id: Owner of the project.
        session: Async database session.
        payload: Project creation payload (name).

    Returns:
        The newly created ``Project`` row.
    """
    new_project = Project(
        id=uuid.uuid4(),
        user_id=user_id,
        name=payload.name.strip() or "Untitled Project",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(new_project)
    await session.commit()
    await session.refresh(new_project)
    return new_project


async def list_projects(user_id: uuid.UUID, session: AsyncSession) -> list[Project]:
    """List every project owned by the given user, oldest-first.

    Args:
        user_id: Owner whose projects to fetch.
        session: Async database session.

    Returns:
        List of ``Project`` objects ordered by ``created_at`` ascending.
    """
    stmt = select(Project).where(Project.user_id == user_id).order_by(Project.created_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_project(
    user_id: uuid.UUID, session: AsyncSession, project_id: uuid.UUID
) -> Project | None:
    """Retrieve a single project by ID, scoped to the given user.

    Args:
        user_id: Owner to match against.
        session: Async database session.
        project_id: The project to look up.

    Returns:
        The ``Project`` if found and owned by ``user_id``, else ``None``.
    """
    stmt = select(Project).where(Project.id == project_id).where(Project.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_project(
    payload: ProjectUpdate,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    session: AsyncSession,
) -> Project | None:
    """Rename an existing project (the only mutable field today).

    Args:
        payload: Partial update — `name` is the only field consumed.
        user_id: Owner to match against (ownership check).
        project_id: The project to rename.
        session: Async database session.

    Returns:
        The updated ``Project``, or ``None`` if not found / not owned.
    """
    project = await get_project(user_id, session, project_id)
    if project is None:
        return None

    if payload.name is not None:
        next_name = payload.name.strip()
        if next_name:
            project.name = next_name

    project.updated_at = datetime.now()
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(user_id: uuid.UUID, session: AsyncSession, project_id: uuid.UUID) -> bool:
    """Delete an existing project owned by the given user.

    Linked conversations have their ``project_id`` cleared by the FK's
    ``ON DELETE SET NULL`` rule — they survive the deletion.

    Returns:
        ``True`` when a project was deleted, otherwise ``False``.
    """
    project = await get_project(user_id, session, project_id)
    if project is None:
        return False

    await session.delete(project)
    await session.commit()
    return True
