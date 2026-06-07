"""paw conversations — create, send, list, show, rename, delete, export.

This is the headline subcommand of the agent CLI: it drives the same
UUID-first flow the frontend uses — generate a v4 UUID locally, POST
``/api/v1/conversations/{uuid}`` to persist the row, then POST
``/api/v1/chat/`` with ``conversation_id`` populated and consume the
resulting SSE stream. See ``frontend/features/chat/hooks/use-chat.ts``
for the canonical client sequence.

Why a single sub-Typer app instead of many top-level commands: keeps
the verb namespace tidy (``paw conversations ...``) and lets every
subcommand share the persona-loading + JSON/plain output plumbing
without duplicating it.

Output modes (consistent across every subcommand):

- ``--json``  : machine-readable JSON on stdout.
- ``--plain`` : tab-separated values (list-shaped commands only).
- default     : human-readable text on stdout, status/progress on stderr.

Exit codes are inherited from ``app.cli.paw.errors`` — local errors
(1), auth errors (3), backend unreachable (4), API errors (5).
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import typer

from app.cli.paw import ids
from app.cli.paw.commands.conversation_mutations import register_conversation_mutation_commands
from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

# Default cap on conversations returned by `paw conversations ls`. Mirrors
# the chat sidebar's "first page" without paging UI complexity for v1.
DEFAULT_LIST_LIMIT = 50

# Hard timeout for a single `paw conversations send` turn. SSE streams
# can run for tens of seconds with tool-use loops; this cap is the
# "something is wrong" backstop, not a typical-turn budget.
DEFAULT_SEND_TIMEOUT_SECONDS = 180.0

# Width allotted to each column when rendering `paw conversations ls`
# in human mode. Sized so a 40-char title + 25-char model fit on an
# 80-col terminal without wrapping.
LS_ID_WIDTH = 36
LS_TITLE_WIDTH = 40
LS_MODEL_WIDTH = 25

# Sole HTTP status code interpreted at this layer (delete-noop semantics).
HTTP_NOT_FOUND = 404

app = typer.Typer(
    help="Manage conversations and send chat turns. Drives the UUID-first flow.",
    no_args_is_help=True,
)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _stderr(message: str) -> None:
    """Write a progress line to stderr (never stdout)."""
    sys.stderr.write(message)
    if not message.endswith("\n"):
        sys.stderr.write("\n")
    sys.stderr.flush()


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #


@app.command("create")
def create(
    workspace: str | None = typer.Option(None, "--workspace", help="Workspace ID override."),
    model: str | None = typer.Option(
        None, "--model", help="Model ID to associate with the conversation."
    ),
    title: str | None = typer.Option(
        None, "--title", help="Initial title (server may regenerate on first turn)."
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Create a new conversation.

    Generates a v4 UUID client-side and POSTs to /api/v1/conversations/{uuid}.
    Persists the new ID as ``current_conversation_id`` in the persona state
    so subsequent ``paw conversations send`` calls without ``--conversation``
    target the right row.

    Examples:
      paw conversations create
      paw conversations create --title "Q2 planning" --json
      paw conversations create --model gpt-4o --workspace ws-1
    """
    state = load_state(profile)
    new_id = ids.new_conversation_id()
    conversation = asyncio.run(
        _create_conversation(state, new_id, title=title, model=model, workspace=workspace)
    )

    state.current_conversation_id = new_id
    state.save()

    if json_out:
        emit_json(conversation)
        return
    emit_human(
        f"Created conversation {conversation['id']}\n"
        f"  title:  {conversation.get('title') or '<empty>'}\n"
        f"  model:  {conversation.get('model_id') or '<default>'}\n"
    )


async def _create_conversation(
    state: PersonaState,
    conversation_id: str,
    *,
    title: str | None,
    model: str | None,
    workspace: str | None,
) -> dict[str, Any]:
    """POST /api/v1/conversations/{id} with the requested body shape."""
    # ConversationCreate accepts {id, title}; model_id / workspace_id aren't
    # part of the create body today but are listed in the plan so we surface
    # them in the JSON output for diagnostics. The server picks the active
    # workspace from the user context.
    body: dict[str, Any] = {}
    if title is not None:
        body["title"] = title
    async with PawClient(state) as client:
        resp = await client.request(
            "POST",
            f"/api/v1/conversations/{conversation_id}",
            json_body=body,
            expect=(200, 201),
        )
    data: dict[str, Any] = resp.json()
    if model is not None:
        data["model_id_requested"] = model
    if workspace is not None:
        data["workspace_id_requested"] = workspace
    return data


# --------------------------------------------------------------------------- #
# send
# --------------------------------------------------------------------------- #


@app.command("send")
def send(
    text: str = typer.Argument(..., help="The user message to send."),
    conversation: str | None = typer.Option(
        None, "--conversation", help="Existing conversation ID."
    ),
    new: bool = typer.Option(False, "--new", help="Create a fresh conversation and send to it."),
    model: str | None = typer.Option(None, "--model"),
    reasoning_effort: str | None = typer.Option(None, "--reasoning-effort"),
    workspace: str | None = typer.Option(None, "--workspace"),
    title: str | None = typer.Option(None, "--title", help="Initial title when --new is used."),
    timeout: float = typer.Option(
        DEFAULT_SEND_TIMEOUT_SECONDS,
        "--timeout",
        help="SSE stream timeout in seconds.",
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Send a chat turn to a conversation (creating one if --new).

    Streams the SSE response, accumulates ``delta``+``message`` content into
    ``final_text``, counts events by type, and re-fetches the conversation
    afterward so ``codex_thread_id`` (set by the openai_codex provider on
    first turn) is included in the output.

    Examples:
      paw conversations send "hello" --new --json
      paw conversations send "follow-up" --conversation 6c87...
      paw conversations send "deep dive" --new --reasoning-effort high -v
    """
    if not new and not conversation:
        raise LocalError(
            "Pass --conversation ID or --new.",
            hint="paw conversations send 'hi' --new",
        )
    if new and conversation:
        raise LocalError(
            "Pass --conversation or --new, not both.",
        )

    state = load_state(profile)
    result = asyncio.run(
        _send_turn(
            state,
            text=text,
            conversation_id=conversation,
            create_new=new,
            title=title,
            model=model,
            reasoning_effort=reasoning_effort,
            workspace=workspace,
            timeout_seconds=timeout,
            verbose=verbose,
        )
    )

    state.current_conversation_id = result["conversation_id"]
    state.save()

    if json_out:
        emit_json(result)
        return

    emit_human(result["final_text"] or "")
    deltas = result["events"].get("delta", 0)
    emit_human(
        f"[conversation {result['conversation_id']} | "
        f"model {result.get('model_id') or '<default>'} | "
        f"{deltas} deltas | {result['duration_ms']}ms]"
    )


async def _send_turn(
    state: PersonaState,
    *,
    text: str,
    conversation_id: str | None,
    create_new: bool,
    title: str | None,
    model: str | None,
    reasoning_effort: str | None,
    workspace: str | None,
    timeout_seconds: float,
    verbose: bool,
) -> dict[str, Any]:
    """Drive create (if --new) + chat SSE stream + post-stream conversation fetch."""
    start = time.monotonic()
    async with PawClient(state, timeout=timeout_seconds, verbose=verbose) as client:
        # 1. Create the row first so ChatRequest.conversation_id (required)
        #    points at a real UUID.
        if create_new:
            conversation_id = ids.new_conversation_id()
            body: dict[str, Any] = {}
            if title is not None:
                body["title"] = title
            await client.request(
                "POST",
                f"/api/v1/conversations/{conversation_id}",
                json_body=body,
                expect=(200, 201),
            )
            _stderr(f"created conversation {conversation_id}")

        assert conversation_id is not None  # narrowed by branches above

        # 2. Stream the chat turn.
        model_id = model
        if create_new and model_id is None:
            model_id = await _first_available_model_id(client)
        chat_body: dict[str, Any] = {
            "question": text,
            "conversation_id": conversation_id,
        }
        if model_id is not None:
            chat_body["model_id"] = model_id
        if reasoning_effort is not None:
            chat_body["reasoning_effort"] = reasoning_effort

        event_counts: dict[str, int] = {}
        final_text_parts: list[str] = []
        error_payload: dict[str, Any] | None = None

        chat_path = "/api/v1/chat/"
        async for event in client.stream_events(
            method="POST",
            url=chat_path,
            json_body=chat_body,
        ):
            event_type = event.get("type", "unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            if event_type in ("delta", "message"):
                content = event.get("content")
                if isinstance(content, str):
                    final_text_parts.append(content)
            elif event_type == "error":
                error_payload = event

        # 3. Re-fetch the conversation so codex_thread_id (set by the
        #    openai_codex provider on first turn) is in the output.
        follow_up = await client.request(
            "GET",
            f"/api/v1/conversations/{conversation_id}",
            expect=(200,),
        )
        conversation = follow_up.json() or {}

    duration_ms = int((time.monotonic() - start) * 1000)
    output: dict[str, Any] = {
        "conversation_id": conversation_id,
        "model_id": conversation.get("model_id"),
        "codex_thread_id": conversation.get("codex_thread_id"),
        "final_text": "".join(final_text_parts),
        "events": event_counts,
        "duration_ms": duration_ms,
    }
    if workspace is not None:
        output["workspace_id_requested"] = workspace
    if error_payload is not None:
        output["error"] = error_payload
    return output


async def _first_available_model_id(client: PawClient) -> str:
    """Return the first authenticated model from the backend catalog."""
    resp = await client.request("GET", "/api/v1/models", expect=(200,))
    body = resp.json()
    models = body.get("models") if isinstance(body, dict) else None
    if not isinstance(models, list):
        raise LocalError("Could not resolve a model for the new conversation.")
    for row in models:
        if isinstance(row, dict):
            model_id = row.get("model_id") or row.get("id")
            if isinstance(model_id, str) and model_id:
                return model_id
    raise LocalError(
        "No authenticated models are available.",
        hint="Pass --model after configuring a provider, or run `paw models ls`.",
    )


# --------------------------------------------------------------------------- #
# ls
# --------------------------------------------------------------------------- #


@app.command("ls")
def ls(
    limit: int = typer.Option(DEFAULT_LIST_LIMIT, "--limit"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List conversations, most recent first.

    The backend currently returns the full list as a bare JSON array
    (no envelope); ``--limit`` is applied client-side. If the endpoint
    later switches to an envelope, ``_extract_conversations`` will
    accept both shapes without breaking callers.

    Examples:
      paw conversations ls
      paw conversations ls --json --limit 10
      paw conversations ls --plain
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    state = load_state(profile)
    conversations = asyncio.run(_list_conversations(state, limit))

    if json_out:
        emit_json(conversations)
        return
    if plain:
        emit_plain_rows(
            (c["id"], c.get("title", ""), c.get("model_id") or "", c.get("updated_at", ""))
            for c in conversations
        )
        return

    header = (
        f"{'ID':<{LS_ID_WIDTH}}  {'TITLE':<{LS_TITLE_WIDTH}}  {'MODEL':<{LS_MODEL_WIDTH}}  UPDATED"
    )
    emit_human(header)
    for c in conversations:
        title = (c.get("title") or "")[:LS_TITLE_WIDTH]
        model = (c.get("model_id") or "")[:LS_MODEL_WIDTH]
        emit_human(
            f"{c['id']:<{LS_ID_WIDTH}}  "
            f"{title:<{LS_TITLE_WIDTH}}  "
            f"{model:<{LS_MODEL_WIDTH}}  "
            f"{c.get('updated_at', '')}"
        )


def _extract_conversations(payload: Any) -> list[dict[str, Any]]:
    """Accept both bare-list and ``{conversations: [...]}`` envelope shapes."""
    if isinstance(payload, list):
        return [c for c in payload if isinstance(c, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("conversations"), list):
        return [c for c in payload["conversations"] if isinstance(c, dict)]
    return []


async def _list_conversations(state: PersonaState, limit: int) -> list[dict[str, Any]]:
    """GET /api/v1/conversations and apply the client-side limit."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/api/v1/conversations", expect=(200,))
    return _extract_conversations(resp.json())[:limit]


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #


@app.command("show")
def show(
    conversation_id: str = typer.Argument(...),
    with_messages: bool = typer.Option(False, "--with-messages"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Fetch a conversation; optionally include its message history.

    Examples:
      paw conversations show 6c87... --json
      paw conversations show 6c87... --with-messages --json
    """
    state = load_state(profile)
    result = asyncio.run(_show_conversation(state, conversation_id, with_messages=with_messages))

    if json_out:
        emit_json(result)
        return

    conv = result["conversation"]
    emit_human(
        f"{conv.get('id')}  {conv.get('title') or '<empty>'}\n"
        f"  model:           {conv.get('model_id') or '<default>'}\n"
        f"  codex_thread_id: {conv.get('codex_thread_id') or '<none>'}\n"
        f"  updated_at:      {conv.get('updated_at') or '<none>'}"
    )
    if with_messages:
        emit_human(f"\n{len(result.get('messages') or [])} messages")


async def _show_conversation(
    state: PersonaState,
    conversation_id: str,
    *,
    with_messages: bool,
) -> dict[str, Any]:
    """Fetch the conversation row, plus messages when requested."""
    async with PawClient(state) as client:
        conv_resp = await client.request(
            "GET",
            f"/api/v1/conversations/{conversation_id}",
            expect=(200,),
        )
        result: dict[str, Any] = {"conversation": conv_resp.json()}
        if with_messages:
            msg_resp = await client.request(
                "GET",
                f"/api/v1/conversations/{conversation_id}/messages",
                expect=(200,),
            )
            result["messages"] = msg_resp.json()
    return result


register_conversation_mutation_commands(app)
