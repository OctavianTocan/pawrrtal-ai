"""Local operator commands for one-off dev account setup.

These commands intentionally work against the configured local database
instead of the public HTTP API. They are for trusted machine operators who
need to bootstrap a user, pin a workspace path, or repair a channel binding
before the user can log in through the normal app flow.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import typer
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import UserAlreadyExists, UserNotExists
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json
from app.infrastructure.auth.users import UserManager
from app.infrastructure.database.legacy import User, async_session_maker
from app.infrastructure.models.channel import ChannelBinding
from app.infrastructure.models.workspace import Workspace
from app.schemas import UserCreate

app = typer.Typer(
    help="Trusted local operator commands for user/workspace/channel bootstrap.",
    no_args_is_help=True,
)


@dataclass
class SeedUserResult:
    """Machine-readable result for ``paw admin seed-user``."""

    email: str
    user_id: str
    workspace_id: str
    workspace_path: str
    created_user: bool
    generated_password: str | None
    telegram_id: str | None
    telegram_chat_id: str | None
    telegram_display_handle: str | None


@app.command("seed-user")
def seed_user(
    email: str = typer.Option(..., "--email", help="User email to create or update."),
    password: str | None = typer.Option(
        None,
        "--password",
        help="Password for a new user. Omit to generate one.",
    ),
    workspace_name: str = typer.Option("Main", "--workspace-name"),
    workspace_slug: str = typer.Option("main", "--workspace-slug"),
    workspace_path: Path = typer.Option(
        ...,
        "--workspace-path",
        help="Absolute Pawrrtal workspace path to store in the DB.",
    ),
    symlink_target: Path | None = typer.Option(
        None,
        "--symlink-target",
        help="Create --workspace-path as a symlink to this existing directory.",
    ),
    telegram_id: str | None = typer.Option(None, "--telegram-id"),
    telegram_chat_id: str | None = typer.Option(None, "--telegram-chat-id"),
    telegram_handle: str | None = typer.Option(None, "--telegram-handle"),
    claim_telegram: bool = typer.Option(
        False,
        "--claim-telegram",
        help="Reassign an existing Telegram binding from another Pawrrtal user.",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Create/update a local user, default workspace, and Telegram binding.

    This is idempotent for the same email + workspace slug. It never deletes
    workspace files. When ``--symlink-target`` is provided, the command creates
    ``--workspace-path`` as a symlink and refuses to overwrite conflicting
    paths.
    """
    result = asyncio.run(
        _seed_user(
            email=email,
            password=password,
            workspace_name=workspace_name,
            workspace_slug=workspace_slug,
            workspace_path=workspace_path,
            symlink_target=symlink_target,
            telegram_id=telegram_id,
            telegram_chat_id=telegram_chat_id,
            telegram_handle=telegram_handle,
            claim_telegram=claim_telegram,
        )
    )
    payload = asdict(result)
    if json_out:
        emit_json(payload)
        return

    lines = [
        "user seeded.",
        f"  email:      {result.email}",
        f"  user_id:    {result.user_id}",
        f"  workspace:  {result.workspace_id}",
        f"  path:       {result.workspace_path}",
    ]
    if result.created_user:
        lines.append(f"  password:   {result.generated_password}")
    if result.telegram_id:
        lines.append(f"  telegram:   {result.telegram_id}")
    emit_human("\n".join(lines))


async def _seed_user(
    *,
    email: str,
    password: str | None,
    workspace_name: str,
    workspace_slug: str,
    workspace_path: Path,
    symlink_target: Path | None,
    telegram_id: str | None,
    telegram_chat_id: str | None,
    telegram_handle: str | None,
    claim_telegram: bool,
) -> SeedUserResult:
    """Run the trusted local seed workflow."""
    _validate_telegram_options(
        telegram_id=telegram_id,
        telegram_chat_id=telegram_chat_id,
        telegram_handle=telegram_handle,
        claim_telegram=claim_telegram,
    )
    resolved_workspace_path = _prepare_workspace_path(workspace_path, symlink_target)
    created_password: str | None = None

    async with async_session_maker() as session:
        user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)
        try:
            user = await manager.get_by_email(email)
        except UserNotExists:
            created_password = password or secrets.token_urlsafe(24)
            try:
                user = await manager.create(
                    UserCreate(email=email, password=created_password),
                    safe=False,
                )
            except UserAlreadyExists:
                user = await manager.get_by_email(email)
                created_password = None

        workspace = await _upsert_workspace(
            user_id=user.id,
            name=workspace_name,
            slug=workspace_slug,
            path=resolved_workspace_path,
            session=session,
        )
        if telegram_id is not None:
            await _upsert_telegram_binding(
                user_id=user.id,
                telegram_id=telegram_id,
                chat_id=telegram_chat_id or telegram_id,
                handle=telegram_handle,
                claim=claim_telegram,
                session=session,
            )
        await session.commit()

    return SeedUserResult(
        email=email,
        user_id=str(user.id),
        workspace_id=str(workspace.id),
        workspace_path=str(resolved_workspace_path),
        created_user=created_password is not None,
        generated_password=created_password,
        telegram_id=telegram_id,
        telegram_chat_id=telegram_chat_id or telegram_id,
        telegram_display_handle=telegram_handle,
    )


def _validate_telegram_options(
    *,
    telegram_id: str | None,
    telegram_chat_id: str | None,
    telegram_handle: str | None,
    claim_telegram: bool,
) -> None:
    """Reject partial Telegram binding inputs before touching local state."""
    if telegram_id is not None:
        return
    if telegram_chat_id is not None or telegram_handle is not None or claim_telegram:
        raise LocalError(
            "--telegram-id is required when passing Telegram binding options.",
            hint="Pass --telegram-id, or omit all Telegram options.",
        )


def _prepare_workspace_path(workspace_path: Path, symlink_target: Path | None) -> Path:
    """Create or validate the requested workspace path."""
    if not workspace_path.is_absolute():
        raise LocalError("--workspace-path must be absolute.")
    if symlink_target is None:
        workspace_path.mkdir(parents=True, exist_ok=True)
        return workspace_path

    if not symlink_target.is_absolute():
        raise LocalError("--symlink-target must be absolute.")
    if not symlink_target.is_dir():
        raise LocalError(f"--symlink-target does not exist or is not a directory: {symlink_target}")

    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    if workspace_path.is_symlink():
        existing_target = workspace_path.readlink()
        if existing_target == symlink_target:
            return workspace_path
        raise LocalError(f"{workspace_path} points to {existing_target}, not {symlink_target}")
    if workspace_path.exists():
        raise LocalError(f"{workspace_path} exists and is not a symlink.")
    workspace_path.symlink_to(symlink_target)
    return workspace_path


async def _upsert_workspace(
    *,
    user_id: uuid.UUID,
    name: str,
    slug: str,
    path: Path,
    session: AsyncSession,
) -> Workspace:
    """Create or update the user's named workspace and make it default."""
    result = await session.execute(
        select(Workspace).where(Workspace.user_id == user_id, Workspace.slug == slug).limit(1)
    )
    workspace: Workspace | None = result.scalar_one_or_none()
    if workspace is None:
        workspace = Workspace(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            slug=slug,
            path=str(path),
            is_default=True,
            created_at=datetime.now(UTC),
        )
        session.add(workspace)
    else:
        workspace.name = name
        workspace.path = str(path)
        workspace.is_default = True

    await session.execute(
        update(Workspace)
        .where(Workspace.user_id == user_id, Workspace.id != workspace.id)
        .values(is_default=False)
    )
    return workspace


async def _upsert_telegram_binding(
    *,
    user_id: uuid.UUID,
    telegram_id: str,
    chat_id: str,
    handle: str | None,
    claim: bool,
    session: AsyncSession,
) -> None:
    """Create/update the Telegram binding for a seeded user."""
    result = await session.execute(
        select(ChannelBinding)
        .where(
            ChannelBinding.provider == "telegram", ChannelBinding.external_user_id == telegram_id
        )
        .limit(1)
    )
    binding = result.scalar_one_or_none()
    if binding is not None and binding.user_id != user_id and not claim:
        raise LocalError(
            f"Telegram ID {telegram_id} is already bound to user {binding.user_id}.",
            hint="Pass --claim-telegram to reassign it.",
        )
    if binding is None:
        binding = ChannelBinding(
            id=uuid.uuid4(),
            user_id=user_id,
            provider="telegram",
            external_user_id=telegram_id,
            external_chat_id=chat_id,
            display_handle=handle,
            created_at=datetime.now(UTC),
            has_topics_enabled=False,
        )
        session.add(binding)
        return

    binding.user_id = user_id
    binding.external_chat_id = chat_id
    binding.display_handle = handle
    binding.has_topics_enabled = False
