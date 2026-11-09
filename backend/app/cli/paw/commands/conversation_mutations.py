"""Mutation and export commands for `paw conversations`."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import ApiError, LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json

HTTP_NOT_FOUND = 404


def register_conversation_mutation_commands(app: typer.Typer) -> None:
    """Attach rename/delete/export commands to the conversations Typer."""

    @app.command("rename")
    def rename(
        conversation_id: str = typer.Argument(...),
        new_title: str = typer.Argument(...),
        profile: str = typer.Option("default", "--profile"),
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        """Rename a conversation."""
        state = load_state(profile)
        result = asyncio.run(_rename_conversation(state, conversation_id, new_title))
        if json_out:
            emit_json(result)
            return
        emit_human(f"renamed {conversation_id} -> {result['title']}")

    @app.command("delete")
    def delete(
        conversation_id: str = typer.Argument(...),
        yes: bool = typer.Option(False, "--yes", "-y"),
        profile: str = typer.Option("default", "--profile"),
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        """Delete a conversation. Idempotent: missing rows return deleted=false, exit 0."""
        if not yes:
            raise LocalError(
                "Pass --yes to confirm deletion.",
                hint="paw conversations delete <id> --yes",
            )
        state = load_state(profile)
        result = asyncio.run(_delete_conversation(state, conversation_id))
        if json_out:
            emit_json(result)
            return
        if result["deleted"]:
            emit_human(f"deleted {conversation_id}")
        else:
            emit_human(f"not found: {conversation_id}")

    @app.command("export")
    def export(
        conversation_id: str = typer.Argument(...),
        export_format: str = typer.Option("md", "--format", help="md | json"),
        profile: str = typer.Option("default", "--profile"),
    ) -> None:
        """Export a conversation as Markdown transcript or raw JSON message envelope."""
        if export_format not in ("md", "json"):
            raise LocalError(
                f"Unknown --format {export_format!r}.",
                hint="--format md  |  --format json",
            )
        state = load_state(profile)
        messages = asyncio.run(_fetch_messages(state, conversation_id))
        if export_format == "json":
            emit_json({"id": conversation_id, "messages": messages})
            return
        emit_human(_render_markdown_transcript(conversation_id, messages))


async def _rename_conversation(
    state: PersonaState,
    conversation_id: str,
    new_title: str,
) -> dict[str, Any]:
    """POST /api/v1/conversations/{id}/title?first_message=<title>."""
    async with PawClient(state) as client:
        resp = await client.request(
            "POST",
            f"/api/v1/conversations/{conversation_id}/title",
            params={"first_message": new_title},
            expect=(200,),
        )
    body = resp.json()
    # The endpoint returns the generated title as a bare JSON string.
    title = body if isinstance(body, str) else (body.get("title") if isinstance(body, dict) else "")
    return {"id": conversation_id, "title": title}


async def _delete_conversation(state: PersonaState, conversation_id: str) -> dict[str, Any]:
    """DELETE /api/v1/conversations/{id}; treat 404 as deleted=false, exit 0."""
    async with PawClient(state) as client:
        try:
            await client.request(
                "DELETE",
                f"/api/v1/conversations/{conversation_id}",
                expect=(204,),
            )
        except ApiError as e:
            if e.status_code == HTTP_NOT_FOUND:
                return {"deleted": False, "reason": "not_found", "id": conversation_id}
            raise
    return {"deleted": True, "id": conversation_id}


async def _fetch_messages(state: PersonaState, conversation_id: str) -> list[dict[str, Any]]:
    """GET /api/v1/conversations/{id}/messages."""
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            f"/api/v1/conversations/{conversation_id}/messages",
            expect=(200,),
        )
    body = resp.json()
    return body if isinstance(body, list) else []


def _render_markdown_transcript(conversation_id: str, messages: list[dict[str, Any]]) -> str:
    """Synthesize a Markdown transcript from the messages envelope."""
    lines: list[str] = [f"# Conversation {conversation_id}", ""]
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content") or ""
        lines.append(f"## {role}")
        lines.append("")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)
