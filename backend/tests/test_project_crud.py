"""CRUD service tests for projects."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.crud import (
    create_conversation,
    get_conversation,
    update_conversation,
)
from app.infrastructure.database.legacy import User
from app.projects.crud import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
from app.schemas import (
    ConversationCreate,
    ConversationUpdate,
    ProjectCreate,
    ProjectUpdate,
)


@pytest.mark.anyio
async def test_create_project_persists_name_and_owner(
    db_session: AsyncSession, test_user: User
) -> None:
    """A new project is created with the supplied name + scoped to the user."""
    project = await create_project(test_user.id, db_session, ProjectCreate(name="portfolio"))

    assert project.name == "portfolio"
    assert project.user_id == test_user.id


@pytest.mark.anyio
async def test_create_project_falls_back_to_default_name(
    db_session: AsyncSession, test_user: User
) -> None:
    """An empty name falls back to "Untitled Project" so the row is never blank."""
    project = await create_project(test_user.id, db_session, ProjectCreate(name="   "))

    assert project.name == "Untitled Project"


@pytest.mark.anyio
async def test_list_projects_returns_only_owned(db_session: AsyncSession, test_user: User) -> None:
    """list_projects only returns projects owned by the supplied user."""
    await create_project(test_user.id, db_session, ProjectCreate(name="mine"))

    projects = await list_projects(test_user.id, db_session)
    assert [project.name for project in projects] == ["mine"]
    assert all(project.user_id == test_user.id for project in projects)


@pytest.mark.anyio
async def test_get_project_scoped_to_owner(db_session: AsyncSession, test_user: User) -> None:
    """get_project returns the row when owned, else None for foreign IDs."""
    project = await create_project(test_user.id, db_session, ProjectCreate(name="mine"))

    found = await get_project(test_user.id, db_session, project.id)
    assert found is not None
    assert found.id == project.id

    missing = await get_project(test_user.id, db_session, uuid4())
    assert missing is None


@pytest.mark.anyio
async def test_update_project_renames_in_place(db_session: AsyncSession, test_user: User) -> None:
    """update_project rewrites the name and bumps updated_at."""
    project = await create_project(test_user.id, db_session, ProjectCreate(name="Old"))
    original_updated_at = project.updated_at

    renamed = await update_project(ProjectUpdate(name="New"), test_user.id, project.id, db_session)
    assert renamed is not None
    assert renamed.name == "New"
    assert renamed.updated_at >= original_updated_at


@pytest.mark.anyio
async def test_update_project_ignores_blank_name(db_session: AsyncSession, test_user: User) -> None:
    """A whitespace-only rename leaves the existing name untouched."""
    project = await create_project(test_user.id, db_session, ProjectCreate(name="Original"))

    renamed = await update_project(ProjectUpdate(name="   "), test_user.id, project.id, db_session)
    assert renamed is not None
    assert renamed.name == "Original"


@pytest.mark.anyio
async def test_delete_project_removes_project_row(
    db_session: AsyncSession, test_user: User
) -> None:
    """Deleting a project removes the row + the assigned conversation survives.

    The ON DELETE SET NULL cascade is enforced by Postgres in production but
    not by SQLite without PRAGMA foreign_keys=ON, so this test only asserts
    behaviour the test fixtures can reliably provide: the project goes away
    and the previously-linked conversation still exists.
    """
    project = await create_project(test_user.id, db_session, ProjectCreate(name="container"))
    conversation = await create_conversation(
        test_user.id, db_session, ConversationCreate(title="Linked")
    )
    await update_conversation(
        ConversationUpdate(project_id=project.id, project_id_set=True),
        test_user.id,
        conversation.id,
        db_session,
    )

    deleted = await delete_project(test_user.id, db_session, project.id)
    assert deleted is True

    gone = await get_project(test_user.id, db_session, project.id)
    assert gone is None

    # unwrap to assert the surviving row stayed intact.
    survivor = await get_conversation(test_user.id, db_session, conversation.id)
    assert survivor is not None


@pytest.mark.anyio
async def test_delete_project_returns_false_for_unknown_id(
    db_session: AsyncSession, test_user: User
) -> None:
    """delete_project signals "no row" instead of raising for foreign IDs."""
    deleted = await delete_project(test_user.id, db_session, uuid4())
    assert deleted is False


@pytest.mark.anyio
async def test_assign_then_unassign_conversation_to_project(
    db_session: AsyncSession, test_user: User
) -> None:
    """The PATCH conversation flow can both attach and detach a conversation."""
    project = await create_project(
        test_user.id, db_session, ProjectCreate(name="assignment-target")
    )
    conversation = await create_conversation(
        test_user.id, db_session, ConversationCreate(title="Hi")
    )

    # Attach
    await update_conversation(
        ConversationUpdate(project_id=project.id, project_id_set=True),
        test_user.id,
        conversation.id,
        db_session,
    )
    attached = await get_conversation(test_user.id, db_session, conversation.id)
    assert attached is not None
    assert attached.project_id == project.id

    # Detach via project_id_set + None
    await update_conversation(
        ConversationUpdate(project_id=None, project_id_set=True),
        test_user.id,
        conversation.id,
        db_session,
    )
    detached = await get_conversation(test_user.id, db_session, conversation.id)
    assert detached is not None
    assert detached.project_id is None
