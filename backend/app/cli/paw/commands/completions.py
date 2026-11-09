"""paw completions — composer autocomplete probes."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json

app = typer.Typer(
    help="Exercise composer completion endpoints.",
    no_args_is_help=True,
)


@app.command("autocomplete")
def autocomplete(
    text: str = typer.Argument(..., help="In-progress draft text."),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Fetch a ghost-text continuation for a draft chat message."""
    state = load_state(profile)
    payload = asyncio.run(_autocomplete(state, text=text))
    if json_out:
        emit_json(payload)
        return
    emit_human(str(payload.get("suggestion") or ""))


async def _autocomplete(state: PersonaState, *, text: str) -> dict[str, Any]:
    """POST /api/v1/completions/autocomplete."""
    async with PawClient(state) as client:
        resp = await client.request(
            "POST",
            "/api/v1/completions/autocomplete",
            json_body={"text": text},
            expect=(200,),
        )
    body = resp.json()
    return body if isinstance(body, dict) else {"suggestion": ""}
