"""paw jobs — scheduled-job CRUD.

Drives the same backend surface as the scheduled-jobs settings UI
(``/api/v1/scheduled-jobs`` family). Bindings are scoped per user; a
user can never see another user's jobs through this CLI (the backend
enforces this via ``get_allowed_user``).

Verbs:

- ``paw jobs list / ls``  GET    /api/v1/scheduled-jobs/   (bare list, newest-first)
- ``paw jobs show <id>``  derived from the list response client-side
                            (no per-row GET endpoint exposed)
- ``paw jobs create``     POST   /api/v1/scheduled-jobs/
- ``paw jobs delete <id>``  DELETE /api/v1/scheduled-jobs/{id}   (soft-delete)

Backend surface notes (verified against
``backend/app/api/scheduled_jobs.py`` at implementation time):

- The list endpoint accepts no query params today; ``--active-only``
  filters client-side after the round-trip so we don't lie about a
  server-side filter that does not exist.
- ``POST`` requires either ``cron_expression`` (recurring) or
  ``fire_at`` (one-shot). The scheduler validates ``cron_expression``
  against ``CronTrigger.from_crontab`` server-side; an invalid value
  surfaces as 422.
- ``DELETE`` is soft (flips ``is_active`` to false); historical rows
  remain visible via ``ls`` for audit until purged by other tooling.
- **Not implemented**: ``paw jobs update`` (no ``PATCH`` route on the
  backend despite a ``ScheduledJobUpdate`` schema being defined; the
  schema is reserved for a future endpoint), and ``paw jobs run-now``
  (no manual-trigger endpoint exists today — APScheduler fires on
  the cron/fire_at trigger only).

Output modes mirror ``paw mcp`` / ``paw audit``: ``--json``,
``--plain``, default human-readable. Exit codes come from
``app.cli.paw.errors``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import typer

from app.cli.paw.config import PersonaState
from app.cli.paw.errors import ApiError, LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows

# Column widths for ``paw jobs ls`` on an 80-col terminal: 36-char
# UUID, 24-char name, schedule expression (cron or ISO datetime),
# status, and an active flag.
LS_ID_WIDTH = 36
LS_NAME_WIDTH = 24
LS_SCHEDULE_WIDTH = 24
LS_STATUS_WIDTH = 10
LS_ACTIVE_WIDTH = 6

# Backend constraints from ``ScheduledJobCreate``. Reject out-of-range
# inputs client-side so we surface a friendly hint instead of a 422.
NAME_MIN_LEN = 1
NAME_MAX_LEN = 128
CRON_MIN_LEN = 1
CRON_MAX_LEN = 128

app = typer.Typer(
    help="Manage scheduled jobs (list / show / create / delete).",
    no_args_is_help=True,
)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _require_one_output_mode(*, json_out: bool, plain: bool) -> None:
    """Reject simultaneous --json + --plain. Mutually exclusive by design."""
    if json_out and plain:
        raise LocalError(
            "Pass --json or --plain, not both.",
            hint="--json for machine output, --plain for TSV.",
        )


def _load_state(profile: str) -> PersonaState:
    """Load persona state for ``profile``; surface a friendly hint when absent."""
    try:
        return PersonaState.load(profile)
    except FileNotFoundError as e:
        raise LocalError(
            f"No persona state for profile {profile!r}.",
            hint="Run `paw login` first.",
        ) from e


def _validate_name(name: str) -> None:
    """Reject names outside the backend's StringConstraints bounds."""
    stripped = name.strip()
    if len(stripped) < NAME_MIN_LEN or len(stripped) > NAME_MAX_LEN:
        raise LocalError(
            f"Bad --name (length {len(stripped)}): expected {NAME_MIN_LEN}..{NAME_MAX_LEN} chars.",
            hint="--name 'daily summary'",
        )


def _validate_cron(cron: str) -> None:
    """Reject cron expressions outside the backend's StringConstraints bounds."""
    stripped = cron.strip()
    if len(stripped) < CRON_MIN_LEN or len(stripped) > CRON_MAX_LEN:
        raise LocalError(
            f"Bad --cron (length {len(stripped)}): expected {CRON_MIN_LEN}..{CRON_MAX_LEN} chars.",
            hint="--cron '0 9 * * *'  (every day at 09:00)",
        )


def _parse_fire_at(raw: str) -> str:
    """Validate an ISO-8601 datetime string client-side; return it normalized.

    We don't try to convert timezones — pass through the user's input
    so the backend sees exactly what they intended, while catching the
    bad-format case before the round-trip.
    """
    try:
        # ``fromisoformat`` accepts ``2026-05-30T09:00:00`` and trailing
        # offsets like ``+00:00``. It rejects ``Z`` suffixes on Python
        # < 3.11, but we target 3.13 where ``Z`` parses fine.
        datetime.fromisoformat(raw)
    except ValueError as e:
        raise LocalError(
            f"Bad --at {raw!r}: expected ISO-8601 datetime.",
            hint="--at 2026-05-30T09:00:00Z",
        ) from e
    return raw


def _schedule_summary(job: dict[str, Any]) -> str:
    """Render the schedule axis (cron or fire_at) in a single column."""
    cron = job.get("cron_expression")
    if cron:
        return str(cron)
    fire_at = job.get("fire_at")
    if fire_at:
        return f"@ {fire_at}"
    return "-"


# --------------------------------------------------------------------------- #
# paw jobs list / ls
# --------------------------------------------------------------------------- #


@app.command("list")
def jobs_list(
    active_only: bool = typer.Option(
        False,
        "--active-only",
        help="Hide soft-deleted (is_active=false) rows. Filtered client-side.",
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List every scheduled job the authenticated persona owns.

    The backend returns a bare list of ``ScheduledJobRead`` rows
    newest-first, including soft-deleted rows so historical jobs
    remain inspectable. Use ``--active-only`` to hide them.

    Examples:
      paw jobs list
      paw jobs list --json
      paw jobs list --active-only --plain
    """
    _require_one_output_mode(json_out=json_out, plain=plain)
    state = _load_state(profile)
    jobs = asyncio.run(_list_jobs(state))
    if active_only:
        jobs = [j for j in jobs if j.get("is_active")]

    if json_out:
        emit_json(jobs)
        return
    if plain:
        emit_plain_rows(
            (
                j.get("id"),
                j.get("name"),
                _schedule_summary(j),
                j.get("last_status") or "-",
                "true" if j.get("is_active") else "false",
            )
            for j in jobs
        )
        return

    _emit_ls_human(jobs)


# ``ls`` alias for muscle memory with the other paw resources.
app.command("ls", help="Alias for `list`.")(jobs_list)


def _emit_ls_human(jobs: list[dict[str, Any]]) -> None:
    """Tabular human view: ID + NAME + SCHEDULE + STATUS + ACTIVE."""
    header = (
        f"{'ID':<{LS_ID_WIDTH}}  "
        f"{'NAME':<{LS_NAME_WIDTH}}  "
        f"{'SCHEDULE':<{LS_SCHEDULE_WIDTH}}  "
        f"{'STATUS':<{LS_STATUS_WIDTH}}  "
        f"{'ACTIVE':<{LS_ACTIVE_WIDTH}}"
    )
    emit_human(header)
    for job in jobs:
        job_id = str(job.get("id", ""))[:LS_ID_WIDTH]
        name = str(job.get("name", ""))[:LS_NAME_WIDTH]
        schedule = _schedule_summary(job)[:LS_SCHEDULE_WIDTH]
        status = str(job.get("last_status") or "-")[:LS_STATUS_WIDTH]
        active = "yes" if job.get("is_active") else "no"
        emit_human(
            f"{job_id:<{LS_ID_WIDTH}}  "
            f"{name:<{LS_NAME_WIDTH}}  "
            f"{schedule:<{LS_SCHEDULE_WIDTH}}  "
            f"{status:<{LS_STATUS_WIDTH}}  "
            f"{active:<{LS_ACTIVE_WIDTH}}"
        )


# --------------------------------------------------------------------------- #
# paw jobs show <id>
# --------------------------------------------------------------------------- #


@app.command("show")
def jobs_show(
    job_id: str = typer.Argument(...),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Fetch one scheduled job by ID.

    The backend exposes no per-row GET endpoint; this finds the row
    in the list response client-side. Surfaces a local "not found"
    error when the ID is not in the user's job list.

    Examples:
      paw jobs show 6c87...
      paw jobs show 6c87... --json
    """
    state = _load_state(profile)
    match = asyncio.run(_get_job(state, job_id))

    if json_out:
        emit_json(match)
        return
    emit_human(
        f"{match.get('id')}  {match.get('name')}\n"
        f"  schedule:        {_schedule_summary(match)}\n"
        f"  prompt:          {match.get('prompt')}\n"
        f"  skill:           {match.get('skill_name') or '-'}\n"
        f"  target_chats:    {match.get('target_chat_ids') or []}\n"
        f"  target_conv:     {match.get('target_conversation_id') or '-'}\n"
        f"  working_dir:     {match.get('working_directory') or '-'}\n"
        f"  last_status:     {match.get('last_status') or '-'}\n"
        f"  last_fired_at:   {match.get('last_fired_at') or '-'}\n"
        f"  last_error:      {match.get('last_error') or '-'}\n"
        f"  is_active:       {match.get('is_active')}\n"
        f"  created_at:      {match.get('created_at')}"
    )


# --------------------------------------------------------------------------- #
# paw jobs create
# --------------------------------------------------------------------------- #


@app.command("create")
def jobs_create(
    name: str = typer.Option(
        ..., "--name", help=f"Display name ({NAME_MIN_LEN}..{NAME_MAX_LEN} chars)."
    ),
    prompt: str = typer.Option(..., "--prompt", help="Agent prompt to run when the job fires."),
    cron: str | None = typer.Option(
        None,
        "--cron",
        help="Cron expression (e.g. '0 9 * * *'). Mutually exclusive with --at.",
    ),
    at: str | None = typer.Option(
        None,
        "--at",
        help="One-shot ISO-8601 fire time (e.g. 2026-05-30T09:00:00Z). Mutually exclusive with --cron.",
    ),
    skill: str | None = typer.Option(
        None,
        "--skill",
        help="Optional skill name to prepend to the prompt (e.g. 'triage').",
    ),
    chat_id: list[str] = typer.Option(
        [],
        "--chat-id",
        help="Telegram chat IDs to deliver the result to. Repeat for multiple.",
    ),
    conversation_id: str | None = typer.Option(
        None,
        "--conversation-id",
        help="Optional conversation UUID to persist the agent response into.",
    ),
    working_directory: str | None = typer.Option(
        None,
        "--working-directory",
        help="Override the workspace root for the job's run.",
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Register a new scheduled job for the authenticated persona.

    Exactly one of ``--cron`` or ``--at`` must be supplied. The
    scheduler validates ``cron_expression`` server-side; a malformed
    value surfaces as a 422 (exit 5) rather than at fire time.

    Examples:
      paw jobs create --name daily --prompt 'summarise today' --cron '0 9 * * *'
      paw jobs create --name reminder --prompt 'ping' --at 2026-05-30T09:00:00Z --json
      paw jobs create --name triage --prompt 'review' --cron '*/30 * * * *' --skill triage
    """
    _validate_name(name)
    if cron is None and at is None:
        raise LocalError(
            "Provide either --cron or --at.",
            hint="--cron '0 9 * * *'  or  --at 2026-05-30T09:00:00Z",
        )
    if cron is not None and at is not None:
        raise LocalError(
            "Pass --cron or --at, not both.",
            hint="Cron jobs are recurring; --at is one-shot.",
        )
    if cron is not None:
        _validate_cron(cron)
    fire_at = _parse_fire_at(at) if at is not None else None

    state = _load_state(profile)
    job = asyncio.run(
        _create_job(
            state,
            name=name,
            prompt=prompt,
            cron_expression=cron,
            fire_at=fire_at,
            skill_name=skill,
            target_chat_ids=list(chat_id),
            target_conversation_id=conversation_id,
            working_directory=working_directory,
        )
    )
    if json_out:
        emit_json(job)
        return
    emit_human(
        f"created scheduled job {job.get('id')}\n"
        f"  name:     {job.get('name')}\n"
        f"  schedule: {_schedule_summary(job)}"
    )


# --------------------------------------------------------------------------- #
# paw jobs delete <id>
# --------------------------------------------------------------------------- #


@app.command("delete")
def jobs_delete(
    job_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Soft-delete a scheduled job. Idempotent on 404 (deleted=false).

    The backend flips ``is_active`` to false and removes the live
    trigger; the row remains visible via ``paw jobs ls`` for audit.

    Examples:
      paw jobs delete 6c87... --yes
      paw jobs delete 6c87... --yes --json
    """
    if not yes:
        raise LocalError(
            "Pass --yes to confirm deletion.",
            hint="paw jobs delete <id> --yes",
        )
    state = _load_state(profile)
    result = asyncio.run(_delete_job(state, job_id))
    if json_out:
        emit_json(result)
        return
    if result["deleted"]:
        emit_human(f"deleted {job_id}")
    else:
        emit_human(f"not found: {job_id}")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #


async def _list_jobs(state: PersonaState) -> list[dict[str, Any]]:
    """GET /api/v1/scheduled-jobs/; backend returns a bare list of job rows."""
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            "/api/v1/scheduled-jobs/",
            expect=(200,),
        )
    body = resp.json()
    if not isinstance(body, list):
        return []
    return [j for j in body if isinstance(j, dict)]


async def _get_job(state: PersonaState, job_id: str) -> dict[str, Any]:
    """Resolve one job row by ID via the list endpoint (no per-row GET)."""
    jobs = await _list_jobs(state)
    match = next((j for j in jobs if str(j.get("id")) == job_id), None)
    if match is None:
        raise LocalError(
            f"Scheduled job {job_id} not found.",
            hint="`paw jobs ls` to see available IDs.",
        )
    return match


async def _create_job(
    state: PersonaState,
    *,
    name: str,
    prompt: str,
    cron_expression: str | None,
    fire_at: str | None,
    skill_name: str | None,
    target_chat_ids: list[str],
    target_conversation_id: str | None,
    working_directory: str | None,
) -> dict[str, Any]:
    """POST /api/v1/scheduled-jobs/ with the ScheduledJobCreate body."""
    body: dict[str, Any] = {
        "name": name,
        "prompt": prompt,
        "target_chat_ids": target_chat_ids,
    }
    if cron_expression is not None:
        body["cron_expression"] = cron_expression
    if fire_at is not None:
        body["fire_at"] = fire_at
    if skill_name is not None:
        body["skill_name"] = skill_name
    if target_conversation_id is not None:
        body["target_conversation_id"] = target_conversation_id
    if working_directory is not None:
        body["working_directory"] = working_directory

    async with PawClient(state) as client:
        resp = await client.request(
            "POST",
            "/api/v1/scheduled-jobs/",
            json_body=body,
            expect=(200, 201),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _delete_job(state: PersonaState, job_id: str) -> dict[str, Any]:
    """DELETE /api/v1/scheduled-jobs/{id}; 404 -> deleted=false."""
    async with PawClient(state) as client:
        try:
            await client.request(
                "DELETE",
                f"/api/v1/scheduled-jobs/{job_id}",
                expect=(204,),
            )
        except ApiError as e:
            if "404" in e.message:
                return {"deleted": False, "reason": "not_found", "id": job_id}
            raise
    return {"deleted": True, "id": job_id}
