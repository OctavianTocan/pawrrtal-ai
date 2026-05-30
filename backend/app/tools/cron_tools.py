"""Cron-scheduling agent tools (#313).

Three thin wrappers around :class:`app.agents.scheduling.JobScheduler`:

* ``reminder_schedule`` — register a new recurring or one-shot job (validates the cron expression or date up front).
* ``reminder_list``   — list active scheduled jobs for the current user.
* ``reminder_cancel`` — soft-delete a job by explicit ID.

Safety:

* All tools are user-scoped via ``user_id`` — a tool call cannot
  reach other users' jobs.
* ``reminder_cancel`` requires an explicit job ID (no bulk filters) per
  the issue's "Never allow arbitrary bulk deletion" requirement.
* All tools return ``[scheduler_disabled]`` when
  ``settings.scheduler_enabled`` is False — they don't crash, they
  just tell the model the capability isn't available.

The reminder half of #311 lands on top of these — once the agent can
schedule a job whose prompt is ``"Remind <user> about <topic>"``, the
TASKS.md tools and these cron tools compose into a reminder flow
without any new infrastructure.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from app.agents.scheduling import get_active_scheduler
from app.agents.types import AgentTool
from app.infrastructure.database.legacy import async_session_maker
from app.tools.display import make_tool_display
from app.tools.errors import ToolError, ToolErrorCode

log = logging.getLogger(__name__)

_DISABLED_MSG = (
    "[scheduler_disabled] The scheduler is off on this deployment "
    "(SCHEDULER_ENABLED=false). Tell the user you can't create / list / "
    "delete scheduled jobs here."
)


def _format_job_row(row: dict[str, object]) -> str:
    """Return a one-line summary of a scheduler job dict.

    The dict comes from :meth:`JobScheduler.list_jobs_for_user` — using
    dicts here instead of the :class:`ScheduledJob` ORM type keeps the
    ``core/tools`` layer free of model imports per the import-linter
    contract.
    """
    state = "active" if row.get("is_active") else "inactive"
    prompt = str(row.get("prompt") or "")
    fire_at = row.get("fire_at")
    if isinstance(fire_at, datetime):
        fire_str = f"fire_at={fire_at.isoformat()!r}"
    else:
        fire_str = f"cron={row.get('cron_expression')!r}"
    return f"- {row.get('id')} | {row.get('name')} | {fire_str} | {state} | prompt={prompt[:60]!r}"


def make_reminder_schedule_tool(
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
) -> AgentTool:
    """Return the ``reminder_schedule`` :class:`AgentTool` scoped to ``user_id``."""

    async def execute(tool_call_id: str, **kwargs: Any) -> str:  # noqa: PLR0911
        scheduler = get_active_scheduler()
        if scheduler is None:
            return _DISABLED_MSG
        name = str(kwargs.get("name") or "").strip()
        cron_expression = str(kwargs.get("cron_expression") or "").strip() or None
        fire_at_str = str(kwargs.get("fire_at") or "").strip() or None
        prompt = str(kwargs.get("prompt") or "").strip()

        if not name or not prompt:
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "reminder_schedule requires 'name' and 'prompt'.",
            ).render()

        if bool(cron_expression) == bool(fire_at_str):
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "reminder_schedule requires EXACTLY ONE of 'cron_expression' or 'fire_at'. "
                "Providing both or neither is invalid.",
            ).render()

        fire_at = None
        if fire_at_str:
            try:
                fire_at = datetime.fromisoformat(fire_at_str.replace("Z", "+00:00"))
            except ValueError:
                return ToolError(
                    ToolErrorCode.INVALID_PATH,
                    "Invalid 'fire_at' format. Must be a valid ISO 8601 datetime string.",
                ).render()
        skill_name = kwargs.get("skill_name")
        target_chat_ids = kwargs.get("target_chat_ids")
        if target_chat_ids is not None and not isinstance(target_chat_ids, list):
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "'target_chat_ids' must be a list of strings when supplied.",
            ).render()
        try:
            async with async_session_maker() as session:
                row = await scheduler.add_job(
                    session=session,
                    user_id=user_id,
                    name=name,
                    prompt=prompt,
                    cron_expression=cron_expression,
                    fire_at=fire_at,
                    skill_name=str(skill_name) if skill_name else None,
                    target_chat_ids=[str(c) for c in target_chat_ids] if target_chat_ids else None,
                    target_conversation_id=conversation_id,
                )
        except ValueError as exc:
            return f"[invalid_schedule] {exc}"
        except Exception as exc:
            log.exception("REMINDER_SCHEDULE_FAILED user_id=%s name=%s", user_id, name)
            return f"[error] Could not register reminder: {exc}"

        schedule_desc = (
            f"cron {row.cron_expression!r}"
            if row.cron_expression
            else f"date {row.fire_at.isoformat()!r}"
            if isinstance(row.fire_at, datetime)
            else "date <unknown>"
        )
        return f"Created reminder {row.id} ({row.name!r}) — next fire follows {schedule_desc}."

    return AgentTool(
        name="reminder_schedule",
        description=(
            "Schedule a recurring agent turn or a one-shot reminder. Use when the user asks to "
            "'remind me every morning', 'run this weekly', or otherwise "
            "wants a job to repeat on a schedule or fire once at a specific date. The prompt becomes "
            "the agent input the next time the reminder fires."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short human-readable label for the job.",
                },
                "cron_expression": {
                    "type": "string",
                    "description": (
                        "Standard 5-field cron expression "
                        "(``minute hour day-of-month month day-of-week``). "
                        "Example: ``0 9 * * 1-5`` for 9am on weekdays UTC. "
                        "Mutually exclusive with fire_at."
                    ),
                },
                "fire_at": {
                    "type": "string",
                    "description": (
                        "Specific ISO 8601 datetime string to fire this reminder once. "
                        "Mutually exclusive with cron_expression."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "Agent prompt to run when the cron fires. Keep it "
                        "self-contained — the cron will run in a fresh turn."
                    ),
                },
                "skill_name": {
                    "type": "string",
                    "description": "Optional workspace skill name to bind the run to.",
                },
                "target_chat_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of Telegram chat IDs to deliver the "
                        "result to. Leave unset for default behaviour."
                    ),
                },
            },
            "required": ["name", "prompt"],
        },
        execute=execute,
        display=make_tool_display(
            icon="⏰",
            label="Schedule Reminder",
            present=lambda args: f"⏰ Scheduling Reminder '{str(args.get('name') or '')[:60]}'",
            compact=lambda args: f"Scheduled Reminder '{str(args.get('name') or '')[:40]}'",
        ),
    )


def make_reminder_list_tool(*, user_id: uuid.UUID) -> AgentTool:
    """Return the ``reminder_list`` :class:`AgentTool` scoped to ``user_id``."""

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        scheduler = get_active_scheduler()
        if scheduler is None:
            return _DISABLED_MSG
        include_inactive = bool(kwargs.get("include_inactive"))
        async with async_session_maker() as session:
            rows = await scheduler.list_jobs_for_user(
                session=session,
                user_id=user_id,
                include_inactive=include_inactive,
            )
        if not rows:
            return "No active scheduled jobs." if not include_inactive else "No scheduled jobs."
        return "\n".join(_format_job_row(row) for row in rows)

    return AgentTool(
        name="reminder_list",
        description=(
            "List the calling user's scheduled reminders and cron jobs. Use when the "
            "user asks 'what reminders do I have?' or before scheduling a "
            "new reminder that might duplicate an existing one."
        ),
        parameters={
            "type": "object",
            "properties": {
                "include_inactive": {
                    "type": "boolean",
                    "description": "Include soft-deleted jobs. Defaults to false.",
                }
            },
            "required": [],
        },
        execute=execute,
        display=make_tool_display(
            icon="📅",
            label="List Reminders",
            present=lambda args: (
                "📅 Listing All Reminders"
                if args.get("include_inactive")
                else "📅 Listing Active Reminders"
            ),
            compact=lambda args: "Listed Reminders",
        ),
    )


def make_reminder_cancel_tool(*, user_id: uuid.UUID) -> AgentTool:
    """Return the ``reminder_cancel`` :class:`AgentTool` scoped to ``user_id``."""

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        scheduler = get_active_scheduler()
        if scheduler is None:
            return _DISABLED_MSG
        job_id_raw = str(kwargs.get("job_id") or "").strip()
        if not job_id_raw:
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "reminder_cancel requires an explicit 'job_id' — bulk deletion is not supported.",
            ).render()
        try:
            job_id = uuid.UUID(job_id_raw)
        except ValueError:
            return f"[invalid_job_id] {job_id_raw!r} is not a valid UUID."
        async with async_session_maker() as session:
            # Per-user scope: 404 if the row doesn't exist OR isn't theirs.
            owned = await scheduler.get_job_for_user(
                session=session, user_id=user_id, job_id=job_id
            )
            if owned is None:
                return f"[not_found] No scheduled job {job_id_raw} owned by you."
            removed = await scheduler.remove_job(session=session, job_id=job_id)
        if removed:
            return f"Cancelled scheduled job {job_id_raw}."
        return f"[not_found] Could not remove job {job_id_raw}."

    return AgentTool(
        name="reminder_cancel",
        description=(
            "Cancel a scheduled reminder or cron job by its explicit ID. Bulk filters "
            "are NOT supported — the model must pass a single UUID, "
            "typically obtained from reminder_list first."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": ("UUID of the job to cancel, exactly as returned by cron_list."),
                },
            },
            "required": ["job_id"],
        },
        execute=execute,
        display=make_tool_display(
            icon="🗑",
            label="Cancel Reminder",
            present=lambda args: f"🗑 Canceling Reminder {str(args.get('job_id') or '')[:36]}",
            compact=lambda args: f"Canceled Reminder {str(args.get('job_id') or '')[:8]}…",
        ),
    )
