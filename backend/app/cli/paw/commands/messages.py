"""paw messages — list and inspect persisted chat messages.

The backend exposes only ``GET /api/v1/conversations/{id}/messages``; there is
no ``/messages/{id}`` route and ``ChatMessageRead`` carries no stable per-row
ID — see ``backend/app/schemas.py:326``. To keep ``paw messages get`` useful
anyway, the index into the conversation's ordered message list is the public
handle here (``--conversation CONV --index N``).
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows

# Truncate message content previews in the human ls view; the full
# content is always available via --json.
CONTENT_PREVIEW_WIDTH = 60

app = typer.Typer(
    help="List and inspect persisted chat messages.",
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
    conversation_id: str = typer.Argument(...),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List messages in a conversation in insertion order.

    Backed by ``GET /api/v1/conversations/{id}/messages``.

    Examples:
      paw messages ls conv-1
      paw messages ls conv-1 --json
      paw messages ls conv-1 --plain
    """
    if json_out and plain:
        raise LocalError(
            "Pass --json or --plain, not both.",
            hint="--json for machine output, --plain for TSV.",
        )
    state = _load_state(profile)
    messages = asyncio.run(_fetch_messages(state, conversation_id))

    if json_out:
        emit_json(messages)
        return
    if plain:
        emit_plain_rows(
            (i, m.get("role"), (m.get("content") or "").replace("\n", " "))
            for i, m in enumerate(messages)
        )
        return
    for i, m in enumerate(messages):
        content = (m.get("content") or "").replace("\n", " ")[:CONTENT_PREVIEW_WIDTH]
        emit_human(f"[{i}] {m.get('role'):<9} {content}")


@app.command("get")
def get(
    conversation_id: str = typer.Argument(..., help="Conversation ID owning the message."),
    index: int = typer.Argument(..., help="Zero-based index into the conversation messages list."),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Print a single message by its position in the conversation history.

    The backend's ``ChatMessageRead`` shape does not include a stable per-row
    ID (it's keyed by ``(conversation_id, ordinal)``), so the CLI uses the
    insertion-order index as the public handle. Pair with ``paw messages ls``
    to find the right index.

    Examples:
      paw messages get conv-1 0
      paw messages get conv-1 3 --json
    """
    state = _load_state(profile)
    messages = asyncio.run(_fetch_messages(state, conversation_id))
    if index < 0 or index >= len(messages):
        raise LocalError(
            f"Index {index} out of range; conversation has {len(messages)} message(s).",
            hint="paw messages ls <conv-id> to enumerate.",
        )
    message = messages[index]

    if json_out:
        emit_json(message)
        return
    emit_human(f"role: {message.get('role')}")
    if message.get("thinking"):
        emit_human(f"thinking:\n{message['thinking']}")
    emit_human(f"content:\n{message.get('content') or ''}")


async def _fetch_messages(state: PersonaState, conversation_id: str) -> list[dict[str, Any]]:
    """GET /api/v1/conversations/{id}/messages -> bare list of ChatMessageRead."""
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            f"/api/v1/conversations/{conversation_id}/messages",
            expect=(200,),
        )
    body = resp.json()
    return [m for m in body if isinstance(m, dict)] if isinstance(body, list) else []
