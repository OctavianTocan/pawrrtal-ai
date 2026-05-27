"""paw models — list the backend model catalog filtered to the persona's auth.

The backend already filters ``GET /api/v1/models`` server-side to hosts the
user has credentials for (see ``app/api/models.py:_auth_fingerprint``); there
is no ``include_unauthenticated`` parameter, so ``--all`` is a no-op for now
and documented as such — kept on the CLI surface for forward compatibility if
the backend later grows the filter.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows

# Column widths for the human-mode table on an 80-col terminal.
ID_WIDTH = 36
DISPLAY_WIDTH = 28
HOST_WIDTH = 14

app = typer.Typer(
    help="List models available to the authenticated persona.",
    no_args_is_help=True,
)


def _load_state(profile: str) -> PersonaState:
    """Load persona state for ``profile``; emit a helpful hint when absent."""
    try:
        return PersonaState.load(profile)
    except FileNotFoundError as e:
        raise LocalError(
            f"No persona state for profile {profile!r}.",
            hint="Run `paw login` first.",
        ) from e


@app.command("ls")
def ls(
    show_all: bool = typer.Option(
        False,
        "--all",
        help=(
            "Reserved. Backend currently always filters to authenticated providers — "
            "no server-side toggle exists yet."
        ),
    ),
    host: str | None = typer.Option(None, "--host", help="Filter to a single host (client-side)."),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List models from the backend catalog.

    Iterates the envelope's ``models`` array. ``--host`` filters client-side
    on the ``host`` field (``gemini``, ``openai``, ``anthropic``, ...).

    Examples:
      paw models ls
      paw models ls --json
      paw models ls --host openai --plain
    """
    if json_out and plain:
        raise LocalError(
            "Pass --json or --plain, not both.",
            hint="--json for machine output, --plain for TSV.",
        )
    state = _load_state(profile)
    models = asyncio.run(_list_models(state))
    if host is not None:
        models = [m for m in models if str(m.get("host", "")) == host]
    # show_all is accepted but unused: documented in the option help.
    _ = show_all

    if json_out:
        emit_json(models)
        return
    if plain:
        emit_plain_rows(
            (m.get("id"), m.get("display_name"), m.get("host"), m.get("vendor")) for m in models
        )
        return

    header = f"{'ID':<{ID_WIDTH}}  {'DISPLAY':<{DISPLAY_WIDTH}}  {'HOST':<{HOST_WIDTH}}  VENDOR"
    emit_human(header)
    for m in models:
        emit_human(
            f"{m.get('id', '')!s:<{ID_WIDTH}}  "
            f"{str(m.get('display_name', ''))[:DISPLAY_WIDTH]:<{DISPLAY_WIDTH}}  "
            f"{m.get('host', '')!s:<{HOST_WIDTH}}  "
            f"{m.get('vendor', '')}"
        )


async def _list_models(state: PersonaState) -> list[dict[str, Any]]:
    """GET /api/v1/models -> unwrap the ``{models: [...]}`` envelope."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/api/v1/models", expect=(200,))
    body = resp.json()
    if not isinstance(body, dict):
        return []
    models = body.get("models")
    if not isinstance(models, list):
        return []
    return [m for m in models if isinstance(m, dict)]
