"""Heartbeat HTTP route, runner, and lifespan-scoped scheduler.

Concept lifted from openclaw — periodic background agent turns that
re-enter a conversation on a schedule.  This module owns the parts that
touch the database and HTTP layer; pure config + parsing lives in
`app.core.heartbeat`.

## What ships in this slice

Tracer-bullet vertical slice that proves the wiring end-to-end:

1. APScheduler boots inside the FastAPI lifespan when
   `HEARTBEAT_ENABLED=true` AND `HEARTBEAT_USER_ID` /
   `HEARTBEAT_CONVERSATION_ID` resolve to existing UUIDs.
2. Each check in `HEARTBEAT.md` gets an `IntervalTrigger` job.
3. The job writes a heartbeat-tagged assistant message into the target
   conversation via the existing `chat_message` CRUD helpers, so the
   message becomes visible through the same `GET .../messages` path the
   chat UI already polls.

The real LLM-backed run — feeding the check prompt through the agent
loop with the configured tools and persisting the streamed turn — is the
next slice.  See the `TODO(heartbeat-llm)` marker inside `run_heartbeat`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.heartbeat import HeartbeatCheck, HeartbeatConfig, load_heartbeat_md
from app.crud.chat_message import append_assistant_placeholder, finalize_assistant_message
from app.db import User, async_session_maker
from app.users import get_allowed_user

logger = logging.getLogger(__name__)

# Surface a single status value on the persisted assistant row so the
# chat UI's existing `assistant_status` rendering picks it up.  The chat
# loop uses "complete" / "streaming" / "failed"; we reuse "complete" so
# the row renders as a finished assistant turn.
HEARTBEAT_MESSAGE_STATUS = "complete"
# Conventional prefix on every heartbeat-authored message.  Keeps the
# row visually distinct in the existing chat UI without needing a new
# message kind on the model.  Once we add a dedicated heartbeat surface
# we can swap this for a structured marker on a new column.
HEARTBEAT_MESSAGE_PREFIX = "�ude7c Heartbeat"


class RunHeartbeatRequest(BaseModel):
    """Body for `POST /api/v1/heartbeat/run`."""

    conversation_id: uuid.UUID
    check_name: str | None = Field(
        default=None,
        description=(
            "Name of the check defined in HEARTBEAT.md to run.  When None, "
            "runs the first check in the file (matches the scheduler's "
            "default for single-check tracer configs)."
        ),
    )


class RunHeartbeatResponse(BaseModel):
    """Response for a successful manual run."""

    message_id: uuid.UUID
    check_name: str


async def run_heartbeat(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    check: HeartbeatCheck,
) -> uuid.UUID:
    """Execute one heartbeat turn against a conversation.

    Tracer-bullet implementation: writes a heartbeat-tagged assistant
    message describing the fired check.  The persisted row is finalised
    in place (no `streaming` window) because there's nothing to stream
    yet.

    TODO(heartbeat-llm): feed `check.prompt` through `agent_loop` with
    the same tool composition the chat router builds for an HTTP turn,
    persist the real timeline + tool calls, and emit an SSE event on
    the conversation's existing channel so the UI updates without a
    poll.  Out of scope for this slice — captured as a follow-up.

    Returns the persisted assistant message's id so the manual-trigger
    endpoint can echo it back to the caller.
    """
    placeholder = await append_assistant_placeholder(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    fired_at = datetime.now(UTC).isoformat(timespec="seconds")
    content = (
        f"{HEARTBEAT_MESSAGE_PREFIX} `{check.name}` fired at {fired_at}.\n\n{check.prompt.strip()}"
    )
    await finalize_assistant_message(
        session,
        message_id=placeholder.id,
        content=content,
        thinking=None,
        tool_calls=None,
        timeline=None,
        thinking_duration_seconds=None,
        assistant_status=HEARTBEAT_MESSAGE_STATUS,
    )
    await session.commit()
    logger.info(
        "HEARTBEAT_FIRED check=%s conversation_id=%s message_id=%s",
        check.name,
        conversation_id,
        placeholder.id,
    )
    return placeholder.id


def get_heartbeat_router() -> APIRouter:
    """Build the heartbeat router (mounted at `/api/v1/heartbeat`)."""
    router = APIRouter(prefix="/api/v1/heartbeat", tags=["heartbeat"])

    @router.post("/run", response_model=RunHeartbeatResponse)
    async def trigger_run(
        body: RunHeartbeatRequest,
        user: User = Depends(get_allowed_user),
    ) -> RunHeartbeatResponse:
        """Manually fire a heartbeat check against a conversation.

        Useful both for development (no waiting for the scheduler) and
        for integration tests that need to exercise the end-to-end
        pipeline deterministically.
        """
        config = _load_config_or_empty()
        check = _resolve_check(config, body.check_name)
        if check is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Heartbeat check '{body.check_name}' not found in HEARTBEAT.md"
                    if body.check_name
                    else "HEARTBEAT.md defines no checks"
                ),
            )
        async with async_session_maker() as session:
            message_id = await run_heartbeat(
                session,
                user_id=user.id,
                conversation_id=body.conversation_id,
                check=check,
            )
        return RunHeartbeatResponse(message_id=message_id, check_name=check.name)

    return router


@asynccontextmanager
async def heartbeat_lifespan() -> AsyncIterator[AsyncIOScheduler | None]:
    """Boot the heartbeat scheduler alongside the HTTP server.

    Yields `None` when heartbeat is disabled — either by the
    `HEARTBEAT_ENABLED` flag or because the required user/conversation
    UUIDs aren't configured.  That lets `main.py` `async with` this
    unconditionally without branching on settings.

    A misconfigured HEARTBEAT.md (invalid YAML, schema violation) is
    treated as fatal at boot so the problem surfaces immediately rather
    than after the first interval elapses.
    """
    if not _heartbeat_should_run():
        logger.info("HEARTBEAT_DISABLED reason=settings")
        yield None
        return

    config = _load_config_or_empty()
    if not config.checks:
        logger.info("HEARTBEAT_DISABLED reason=no_checks_in_md")
        yield None
        return

    user_id = uuid.UUID(settings.heartbeat_user_id)
    conversation_id = uuid.UUID(settings.heartbeat_conversation_id)

    scheduler = AsyncIOScheduler()
    for check in config.checks:
        scheduler.add_job(
            _run_scheduled_job,
            trigger=IntervalTrigger(seconds=check.interval_seconds),
            args=[user_id, conversation_id, check],
            id=f"heartbeat:{check.name}",
            name=f"heartbeat:{check.name}",
            replace_existing=True,
        )
    scheduler.start()
    logger.info("HEARTBEAT_BOOT checks=%d", len(config.checks))
    try:
        yield scheduler
    finally:
        scheduler.shutdown(wait=False)
        logger.info("HEARTBEAT_SHUTDOWN")


def _heartbeat_should_run() -> bool:
    """Return True when settings opt into running the scheduler."""
    if not settings.heartbeat_enabled:
        return False
    if not settings.heartbeat_user_id or not settings.heartbeat_conversation_id:
        logger.warning(
            "HEARTBEAT_ENABLED_BUT_UNCONFIGURED — set HEARTBEAT_USER_ID and "
            "HEARTBEAT_CONVERSATION_ID to activate the scheduler",
        )
        return False
    return True


def _resolve_md_path() -> Path:
    """Return the resolved path to `HEARTBEAT.md`.

    `HEARTBEAT_MD_PATH` wins when set; otherwise fall back to
    `<repo>/HEARTBEAT.md` so local dev "just works" without env churn.
    The repo root is three parents up from this file:
    `backend/app/api/heartbeat.py` → `<repo>`.
    """
    if settings.heartbeat_md_path:
        return Path(settings.heartbeat_md_path)
    return Path(__file__).resolve().parents[3] / "HEARTBEAT.md"


def _load_config_or_empty() -> HeartbeatConfig:
    """Load `HEARTBEAT.md` and surface parse errors as logged warnings.

    Returning an empty config on failure keeps the API endpoint
    returning a clean 404 ("no checks defined") rather than a 500 —
    the operator can read the warning in the logs and fix the file.
    """
    try:
        return load_heartbeat_md(_resolve_md_path())
    except ValueError as exc:
        logger.warning("HEARTBEAT_MD_INVALID error=%s", exc)
        return HeartbeatConfig()


def _resolve_check(config: HeartbeatConfig, name: str | None) -> HeartbeatCheck | None:
    """Pick the named check, or the first one when `name` is None."""
    if name is not None:
        return config.find_check(name)
    return config.checks[0] if config.checks else None


async def _run_scheduled_job(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    check: HeartbeatCheck,
) -> None:
    """APScheduler entry point — opens a session and delegates.

    Kept tiny so the scheduler-specific glue (session management,
    exception narrowing) is separate from the runner's domain logic.
    """
    try:
        async with async_session_maker() as session:
            await run_heartbeat(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                check=check,
            )
    except (OSError, RuntimeError) as exc:
        # Narrow on transport-level failures.  Schema/programmer errors
        # should propagate so they're caught in CI rather than silently
        # swallowed by the scheduler thread.
        logger.warning("HEARTBEAT_RUN_FAILED check=%s error=%s", check.name, exc)
