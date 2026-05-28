"""paw cost — cost summary + ledger.

Read-only views over the per-user spend ledger that backs the cost
budget middleware. Mirrors the same backend surface as the user
settings cost gauge (``/api/v1/cost``) and the 402 body emitted when
the rolling cap is exceeded.

Verbs:

- ``paw cost summary``   GET /api/v1/cost   (rolling-window aggregate)
- ``paw cost ledger``    GET /api/v1/cost/ledger   (raw rows, newest-first)

Backend surface notes (verified against ``backend/app/api/cost.py``
at implementation time):

- The summary endpoint takes ``window_hours`` (1..90*24) plus a
  ``breakdown`` toggle for a per-model rollup. There is **no**
  ``since`` / ``until`` / ``workspace`` filter today; the rolling
  window is the only knob. We expose ``--window-hours`` + ``--by
  model`` to match.
- The ledger endpoint paginates by ``limit`` / ``offset`` only — no
  conversation, workspace, or date filters server-side. We expose
  ``--limit`` + ``--offset`` and document the limitation in the
  help text so callers don't expect more.

Output modes mirror ``paw mcp`` / ``paw channels`` / ``paw
workspaces``: ``--json``, ``--plain``, default human-readable.
Exit codes come from ``app.cli.paw.errors``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

# Column widths for `paw cost ledger` on an 80-col terminal: 36-char
# UUID, narrow provider, model id, integer token counts, and the
# 4-decimal USD figure the backend already rounds to.
LEDGER_ID_WIDTH = 36
LEDGER_PROVIDER_WIDTH = 10
LEDGER_MODEL_WIDTH = 28
LEDGER_TOKEN_WIDTH = 8
LEDGER_COST_WIDTH = 10

# Mirrors the backend's clamp (``MAX_SUMMARY_WINDOW_HOURS = 90 * 24``)
# so we surface a friendly local error instead of an opaque 422.
MAX_SUMMARY_WINDOW_HOURS = 90 * 24

# Mirrors ``app.crud.cost.MAX_LIST_LIMIT`` so we reject out-of-range
# values before the round-trip. Imported as a literal here so the CLI
# stays a thin wrapper that doesn't pull in CRUD internals.
MAX_LEDGER_LIMIT = 1000

# Allowed values for ``paw cost summary --by``. Only "model" maps to a
# real backend toggle today (``breakdown=true``); other grouping axes
# are deferred until the backend supports them.
BreakdownAxis = Literal["model"]
ALLOWED_BREAKDOWN_AXES: tuple[BreakdownAxis, ...] = ("model",)

app = typer.Typer(
    help="Cost summary + ledger (read-only views over the per-user spend ledger).",
    no_args_is_help=True,
)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _validate_window_hours(window_hours: int | None) -> None:
    """Reject a window outside the backend's accepted range (1..MAX)."""
    if window_hours is None:
        return
    if window_hours < 1 or window_hours > MAX_SUMMARY_WINDOW_HOURS:
        raise LocalError(
            f"Bad --window-hours {window_hours}: expected 1..{MAX_SUMMARY_WINDOW_HOURS}.",
            hint=f"--window-hours <int between 1 and {MAX_SUMMARY_WINDOW_HOURS}>",
        )


def _validate_breakdown(by: str | None) -> None:
    """Reject a --by axis the backend doesn't support yet."""
    if by is not None and by not in ALLOWED_BREAKDOWN_AXES:
        raise LocalError(
            f"Bad --by {by!r}: expected one of {ALLOWED_BREAKDOWN_AXES}.",
            hint="--by model",
        )


def _validate_ledger_pagination(*, limit: int, offset: int) -> None:
    """Reject limit/offset outside the backend's accepted ranges."""
    if limit < 1 or limit > MAX_LEDGER_LIMIT:
        raise LocalError(
            f"Bad --limit {limit}: expected 1..{MAX_LEDGER_LIMIT}.",
            hint=f"--limit <int between 1 and {MAX_LEDGER_LIMIT}>",
        )
    if offset < 0:
        raise LocalError(
            f"Bad --offset {offset}: must be >= 0.",
            hint="--offset 0",
        )


# --------------------------------------------------------------------------- #
# paw cost summary
# --------------------------------------------------------------------------- #


@app.command("summary")
def cost_summary(
    window_hours: int | None = typer.Option(
        None,
        "--window-hours",
        help=(
            "Rolling window for the aggregate (backend default mirrors the "
            "budget gate). 1..2160 (90 days)."
        ),
    ),
    by: str | None = typer.Option(
        None,
        "--by",
        help="Add a per-axis breakdown. Only `model` is supported by the backend today.",
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Aggregate spend over the rolling cost-budget window.

    The backend exposes a rolling-window aggregate (no since/until
    filter today); ``--window-hours`` overrides the default the
    cost-budget middleware enforces against. ``--by model`` enables
    the per-model breakdown that the settings UI consumes.

    Examples:
      paw cost summary
      paw cost summary --window-hours 24 --by model --json
      paw cost summary --plain
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    _validate_window_hours(window_hours)
    _validate_breakdown(by)
    state = load_state(profile)
    summary = asyncio.run(
        _fetch_cost_summary(
            state,
            window_hours=window_hours,
            breakdown=by == "model",
        )
    )

    if json_out:
        emit_json(summary)
        return
    if plain:
        _emit_summary_plain(summary)
        return
    _emit_summary_human(summary)


def _emit_summary_plain(summary: dict[str, Any]) -> None:
    """TSV rows for the summary scalar fields, then per-model rows when present."""
    rows: list[tuple[Any, ...]] = [
        ("window_hours", summary.get("window_hours")),
        ("current_usd", summary.get("current_usd")),
        ("limit_usd", summary.get("limit_usd")),
        ("remaining_usd", summary.get("remaining_usd")),
    ]
    per_model = summary.get("per_model") or []
    for entry in per_model:
        if not isinstance(entry, dict):
            continue
        rows.append(
            (
                "per_model",
                entry.get("model_id"),
                entry.get("cost_usd"),
                entry.get("turns"),
            )
        )
    emit_plain_rows(rows)


def _emit_summary_human(summary: dict[str, Any]) -> None:
    """Compact human view: window + current/limit + optional model rollup."""
    window = summary.get("window_hours")
    current = summary.get("current_usd")
    limit = summary.get("limit_usd")
    remaining = summary.get("remaining_usd")
    limit_str = f"${limit:.4f}" if isinstance(limit, (int, float)) else "unlimited"
    remaining_str = f"${remaining:.4f}" if isinstance(remaining, (int, float)) else "unlimited"
    current_str = f"${current:.4f}" if isinstance(current, (int, float)) else "n/a"
    emit_human(
        f"window: {window}h\n"
        f"  current:   {current_str}\n"
        f"  limit:     {limit_str}\n"
        f"  remaining: {remaining_str}"
    )
    per_model = summary.get("per_model") or []
    if not per_model:
        return
    emit_human("\nby model:")
    for entry in per_model:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("model_id", "")
        cost = entry.get("cost_usd")
        turns = entry.get("turns")
        cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else "n/a"
        emit_human(f"  {model_id}  {cost_str}  ({turns} turns)")


# --------------------------------------------------------------------------- #
# paw cost ledger
# --------------------------------------------------------------------------- #


@app.command("ledger")
def cost_ledger(
    limit: int = typer.Option(
        100,
        "--limit",
        help=f"Rows per page (1..{MAX_LEDGER_LIMIT}). Newest-first.",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        help="Pagination offset (>= 0).",
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    r"""List raw spend rows for the authenticated persona, newest-first.

    The backend ledger endpoint paginates by limit/offset only. No
    server-side filtering by conversation, workspace, or date is
    available today; use the ``--plain`` TSV output piped through
    ``awk`` / ``grep`` for one-off slicing.

    Examples:
      paw cost ledger
      paw cost ledger --limit 50 --offset 0 --json
      paw cost ledger --plain | awk -F'\\t' '$3=="openai"'
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    _validate_ledger_pagination(limit=limit, offset=offset)
    state = load_state(profile)
    rows = asyncio.run(_fetch_cost_ledger(state, limit=limit, offset=offset))

    if json_out:
        emit_json(rows)
        return
    if plain:
        emit_plain_rows(
            (
                row.get("id"),
                row.get("created_at"),
                row.get("provider"),
                row.get("model_id"),
                row.get("input_tokens"),
                row.get("output_tokens"),
                row.get("cost_usd"),
                row.get("conversation_id"),
            )
            for row in rows
        )
        return

    _emit_ledger_human(rows)


def _emit_ledger_human(rows: list[dict[str, Any]]) -> None:
    """Tabular human view: ID + provider + model + in/out tokens + cost USD."""
    header = (
        f"{'ID':<{LEDGER_ID_WIDTH}}  "
        f"{'PROVIDER':<{LEDGER_PROVIDER_WIDTH}}  "
        f"{'MODEL':<{LEDGER_MODEL_WIDTH}}  "
        f"{'IN':>{LEDGER_TOKEN_WIDTH}}  "
        f"{'OUT':>{LEDGER_TOKEN_WIDTH}}  "
        f"{'USD':>{LEDGER_COST_WIDTH}}"
    )
    emit_human(header)
    for row in rows:
        row_id = str(row.get("id", ""))[:LEDGER_ID_WIDTH]
        provider = str(row.get("provider", ""))[:LEDGER_PROVIDER_WIDTH]
        model = str(row.get("model_id", ""))[:LEDGER_MODEL_WIDTH]
        cost = row.get("cost_usd")
        cost_str = f"{cost:.4f}" if isinstance(cost, (int, float)) else "n/a"
        emit_human(
            f"{row_id:<{LEDGER_ID_WIDTH}}  "
            f"{provider:<{LEDGER_PROVIDER_WIDTH}}  "
            f"{model:<{LEDGER_MODEL_WIDTH}}  "
            f"{row.get('input_tokens', 0)!s:>{LEDGER_TOKEN_WIDTH}}  "
            f"{row.get('output_tokens', 0)!s:>{LEDGER_TOKEN_WIDTH}}  "
            f"{cost_str:>{LEDGER_COST_WIDTH}}"
        )


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #


async def _fetch_cost_summary(
    state: PersonaState,
    *,
    window_hours: int | None,
    breakdown: bool,
) -> dict[str, Any]:
    """GET /api/v1/cost; returns the CostSummaryRead body as a dict.

    ``window_hours`` defaults to the backend's
    ``settings.cost_reset_window_hours`` when omitted, so we forward
    ``None`` by leaving the query param out entirely.
    """
    params: dict[str, Any] = {}
    if window_hours is not None:
        params["window_hours"] = window_hours
    if breakdown:
        params["breakdown"] = "true"
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            "/api/v1/cost/",
            params=params or None,
            expect=(200,),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _fetch_cost_ledger(
    state: PersonaState,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """GET /api/v1/cost/ledger; backend returns a bare list of CostLedgerRead rows."""
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            "/api/v1/cost/ledger",
            params={"limit": limit, "offset": offset},
            expect=(200,),
        )
    body = resp.json()
    if not isinstance(body, list):
        return []
    return [row for row in body if isinstance(row, dict)]
