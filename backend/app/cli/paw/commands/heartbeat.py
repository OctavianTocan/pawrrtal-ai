"""paw heartbeat — HEARTBEAT.md sync operations."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

app = typer.Typer(
    help="Sync workspace HEARTBEAT.md into scheduled jobs.",
    no_args_is_help=True,
)


@app.command("sync")
def heartbeat_sync(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Register the default workspace's HEARTBEAT.md checks as scheduled jobs."""
    require_one_output_mode(json_out=json_out, plain=plain)
    state = load_state(profile)
    payload = asyncio.run(_sync_heartbeat(state))
    if json_out:
        emit_json(payload)
        return
    if plain:
        emit_plain_rows(
            (
                (
                    payload.get("workspace_id"),
                    payload.get("conversation_id"),
                    payload.get("jobs_created"),
                    payload.get("jobs_removed"),
                    payload.get("telegram_linked"),
                ),
            )
        )
        return
    emit_human(
        f"workspace: {payload.get('workspace_id')}\n"
        f"conversation: {payload.get('conversation_id')}\n"
        f"jobs: +{payload.get('jobs_created')} -{payload.get('jobs_removed')}\n"
        f"telegram: {'linked' if payload.get('telegram_linked') else 'not linked'}"
    )


async def _sync_heartbeat(state: PersonaState) -> dict[str, Any]:
    """POST /api/v1/heartbeat/sync."""
    async with PawClient(state) as client:
        resp = await client.request("POST", "/api/v1/heartbeat/sync", expect=(200,))
    body = resp.json()
    return body if isinstance(body, dict) else {}
