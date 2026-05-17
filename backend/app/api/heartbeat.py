"""Heartbeat HTTP route and runner.

Concept lifted from openclaw — periodic background agent turns that
re-enter a conversation on a schedule.  This module owns the parts that
touch the database and HTTP layer; pure config + parsing lives in
`app.core.heartbeat`.

## What ships in this slice

Manual-trigger vertical slice that proves the runner end-to-end:

1. `POST /api/v1/heartbeat/run` loads `HEARTBEAT.md`, picks the named
   (or first) check, and calls `run_heartbeat` to persist a
   heartbeat-tagged assistant message into the conversation.
2. The existing chat UI surfaces the message via the same
   `GET /api/v1/conversations/{id}/messages` path it already polls,
   so no frontend change is needed to see the result.

Scheduled invocation is a deliberate follow-up: pawrrtal already ships
a higher-level `JobScheduler` (see `app.core.scheduler`) for cron-style
work, and registering `run_heartbeat` as a JobScheduler job is the
cleanest seam.  Booting a parallel APScheduler from a lifespan here
would duplicate plumbing.  See the `TODO(heartbeat-scheduler)` marker
below.

The real LLM-backed run — feeding `check.prompt` through the agent
loop with the configured tools and persisting the streamed turn — is
flagged as `TODO(heartbeat-llm)` inside `run_heartbeat`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

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
HEARTBEAT_MESSAGE_PREFIX = "🫀 Heartbeat"


class RunHeartbeatRequest(BaseModel):
    """Body for `POST /api/v1/heartbeat/run`."""

    conversation_id: uuid.UUID
    check_name: str | None = Field(
        default=None,
        description=(
            "Name of the check defined in HEARTBEAT.md to run.  When None, "
            "runs the first check in the file (matches the eventual "
            "scheduler's default for single-check tracer configs)."
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
    persist the real timeline + tool calls, and emit an event on the
    existing EventBus so the UI updates without a poll.  Out of scope
    for this slice — captured as a follow-up.

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
    """Build the heartbeat router (mounted at `/api/v1/heartbeat`).

    TODO(heartbeat-scheduler): register `run_heartbeat` as a
    `JobScheduler` job from the existing scheduler lifespan in
    `main.py`, gated on ``settings.heartbeat_enabled`` and the
    configured user/conversation ids. Out of scope for this slice.
    """
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
