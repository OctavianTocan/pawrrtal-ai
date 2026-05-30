"""paw audit — read-only audit event inspection.

Drives the same backend surface as the audit log views shipped in
``backend/app/api/audit.py``. Bindings are scoped per user; a user
can never see another user's audit events through this CLI (the
backend enforces this via ``get_allowed_user``).

Verbs:

- ``paw audit ls``       GET /api/v1/audit/   (paginated, newest-first)
- ``paw audit show <id>``  derived from the list response client-side
                            (the backend exposes no per-row GET endpoint)

Backend surface notes (verified against ``backend/app/api/audit.py``
at implementation time):

- The list endpoint accepts ``limit`` (1..1000), ``offset`` (>= 0),
  ``event_type`` (exact match), and ``since`` (ISO-8601 datetime).
  No ``until`` / ``actor`` / ``resource_type`` / ``resource_id``
  filters exist server-side today, so we don't expose those flags
  to avoid lying to callers.
- When the audit log is globally disabled the route serves an empty
  list instead of 404 — the CLI treats that as a normal empty page.

Output modes mirror ``paw cost`` / ``paw mcp``: ``--json``,
``--plain``, default human-readable. Exit codes come from
``app.cli.paw.errors``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

# Column widths for `paw audit ls` on an 80-col terminal: 36-char
# UUID, ISO-8601 timestamp, event_type identifier, risk level, and a
# single-char success flag.
LS_ID_WIDTH = 36
LS_CREATED_WIDTH = 20
LS_EVENT_TYPE_WIDTH = 28
LS_RISK_WIDTH = 8
LS_SUCCESS_WIDTH = 7

# Mirrors ``app.governance.audit.crud.MAX_LIST_LIMIT`` so the CLI rejects
# out-of-range values before the round-trip with a friendly hint.
MAX_LIST_LIMIT = 1000

app = typer.Typer(
    help="Inspect audit events (read-only views over the per-user audit log).",
    no_args_is_help=True,
)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _validate_pagination(*, limit: int, offset: int) -> None:
    """Reject limit/offset outside the backend's accepted ranges."""
    if limit < 1 or limit > MAX_LIST_LIMIT:
        raise LocalError(
            f"Bad --limit {limit}: expected 1..{MAX_LIST_LIMIT}.",
            hint=f"--limit <int between 1 and {MAX_LIST_LIMIT}>",
        )
    if offset < 0:
        raise LocalError(
            f"Bad --offset {offset}: must be >= 0.",
            hint="--offset 0",
        )


def _details_summary(details: dict[str, Any] | None) -> str:
    """Short fingerprint of detail keys for the human ls view."""
    if not details:
        return "{}"
    keys = sorted(details.keys())
    return "{" + ", ".join(keys) + "}"


# --------------------------------------------------------------------------- #
# paw audit ls
# --------------------------------------------------------------------------- #


@app.command("ls")
def audit_ls(
    limit: int = typer.Option(
        100,
        "--limit",
        help=f"Rows per page (1..{MAX_LIST_LIMIT}). Newest-first.",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        help="Pagination offset (>= 0).",
    ),
    event_type: str | None = typer.Option(
        None,
        "--event-type",
        help="Filter by exact event_type (e.g. `auth.login`, `chat.turn`).",
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        help="Only events at or after this ISO-8601 timestamp (e.g. 2026-05-01T00:00:00Z).",
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List audit events for the authenticated persona, newest-first.

    The backend list endpoint supports ``limit`` / ``offset`` /
    ``event_type`` / ``since``. No ``until`` / ``actor`` /
    ``resource_type`` / ``resource_id`` filters are available
    server-side today; use ``--plain`` TSV piped through ``awk`` /
    ``grep`` for one-off slicing on those axes.

    Examples:
      paw audit ls
      paw audit ls --event-type auth.login --json
      paw audit ls --since 2026-05-01T00:00:00Z --limit 50
      paw audit ls --plain
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    _validate_pagination(limit=limit, offset=offset)
    state = load_state(profile)
    events = asyncio.run(
        _list_audit_events(
            state,
            limit=limit,
            offset=offset,
            event_type=event_type,
            since=since,
        )
    )

    if json_out:
        emit_json(events)
        return
    if plain:
        emit_plain_rows(
            (
                event.get("id"),
                event.get("created_at"),
                event.get("event_type"),
                event.get("risk_level"),
                "true" if event.get("success") else "false",
                event.get("surface"),
                _details_summary(event.get("details")),
            )
            for event in events
        )
        return

    _emit_ls_human(events)


# `list` alias for muscle memory with the other paw resources.
app.command("list", help="Alias for `ls`.")(audit_ls)


def _emit_ls_human(events: list[dict[str, Any]]) -> None:
    """Tabular human view: ID + CREATED + EVENT_TYPE + RISK + OK."""
    header = (
        f"{'ID':<{LS_ID_WIDTH}}  "
        f"{'CREATED':<{LS_CREATED_WIDTH}}  "
        f"{'EVENT_TYPE':<{LS_EVENT_TYPE_WIDTH}}  "
        f"{'RISK':<{LS_RISK_WIDTH}}  "
        f"{'OK':<{LS_SUCCESS_WIDTH}}"
    )
    emit_human(header)
    for event in events:
        event_id = str(event.get("id", ""))[:LS_ID_WIDTH]
        created = str(event.get("created_at", ""))[:LS_CREATED_WIDTH]
        event_type = str(event.get("event_type", ""))[:LS_EVENT_TYPE_WIDTH]
        risk = str(event.get("risk_level", ""))[:LS_RISK_WIDTH]
        success = "yes" if event.get("success") else "no"
        emit_human(
            f"{event_id:<{LS_ID_WIDTH}}  "
            f"{created:<{LS_CREATED_WIDTH}}  "
            f"{event_type:<{LS_EVENT_TYPE_WIDTH}}  "
            f"{risk:<{LS_RISK_WIDTH}}  "
            f"{success:<{LS_SUCCESS_WIDTH}}"
        )


# --------------------------------------------------------------------------- #
# paw audit show <id>
# --------------------------------------------------------------------------- #


@app.command("show")
def audit_show(
    event_id: str = typer.Argument(...),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Fetch one audit event by ID.

    The backend exposes no per-row GET endpoint; this resolves the
    row by scanning the list response client-side. Surfaces a local
    "not found" error when the ID is not in the user's audit log.

    Because audit events accumulate, ``show`` widens the search to
    the maximum page size to maximise the chance of finding a row
    without paging through the whole history. If you can't find an
    event you expect to be there, narrow ``paw audit ls --since
    <date>`` first.

    Examples:
      paw audit show 6c87...
      paw audit show 6c87... --json
    """
    state = load_state(profile)
    match = asyncio.run(_find_audit_event(state, event_id))
    if match is None:
        raise LocalError(
            f"Audit event {event_id} not found.",
            hint="`paw audit ls` to see available IDs.",
        )

    if json_out:
        emit_json(match)
        return
    details = match.get("details") or {}
    details_str = _details_summary(details) if not details else _format_details(details)
    emit_human(
        f"{match.get('id')}  {match.get('event_type')}\n"
        f"  created:    {match.get('created_at')}\n"
        f"  risk:       {match.get('risk_level')}\n"
        f"  success:    {match.get('success')}\n"
        f"  surface:    {match.get('surface') or '-'}\n"
        f"  request_id: {match.get('request_id') or '-'}\n"
        f"  details:    {details_str}"
    )


def _format_details(details: dict[str, Any]) -> str:
    """Indented key/value rendering for `paw audit show`'s details block."""
    return json.dumps(details, indent=2, sort_keys=True)


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #


async def _list_audit_events(
    state: PersonaState,
    *,
    limit: int,
    offset: int,
    event_type: str | None,
    since: str | None,
) -> list[dict[str, Any]]:
    """GET /api/v1/audit/; backend returns a bare list of AuditEventRead rows."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if event_type is not None:
        params["event_type"] = event_type
    if since is not None:
        params["since"] = since
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            "/api/v1/audit/",
            params=params,
            expect=(200,),
        )
    body = resp.json()
    if not isinstance(body, list):
        return []
    return [row for row in body if isinstance(row, dict)]


async def _find_audit_event(state: PersonaState, event_id: str) -> dict[str, Any] | None:
    """Resolve one audit row by ID via the list endpoint (no per-row GET).

    Searches the most-recent ``MAX_LIST_LIMIT`` rows. Returns ``None``
    when the ID is not in that window so the caller can surface a
    local "not found" error with a useful hint.
    """
    events = await _list_audit_events(
        state,
        limit=MAX_LIST_LIMIT,
        offset=0,
        event_type=None,
        since=None,
    )
    return next((e for e in events if str(e.get("id")) == event_id), None)
