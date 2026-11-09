"""Run-log commands for ``paw lab``."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import PawError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

from .storage import list_runs, load_run, runs_dir

app = typer.Typer(help="Inspect stored lab runs.", no_args_is_help=True)


@app.command("ls")
def runs_ls(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List profile-scoped lab run logs."""
    require_one_output_mode(json_out=json_out, plain=plain)
    load_state(profile)
    rows = list_runs(profile)
    if json_out:
        emit_json(rows)
        return
    if plain:
        emit_plain_rows(
            (row["run_id"], row.get("kind") or "", row.get("model_id") or "") for row in rows
        )
        return
    for row in rows:
        emit_human(
            f"{row['run_id']}\t{row.get('kind') or ''}\t"
            f"{row.get('model_id') or ''}\t{row.get('created_at') or ''}"
        )


@app.command("show")
def runs_show(
    run_id: str = typer.Argument(...),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show one stored run log."""
    load_state(profile)
    payload = load_run(profile, run_id)
    if json_out:
        emit_json(payload)
        return
    emit_human(json.dumps(payload, indent=2, sort_keys=True))


@app.command("export")
def runs_export(
    run_id: str = typer.Argument(...),
    export_format: str = typer.Option("jsonl", "--format", help="jsonl or md."),
    profile: str = typer.Option("default", "--profile"),
) -> None:
    """Export one stored run as JSONL or Markdown."""
    load_state(profile)
    payload = load_run(profile, run_id)
    if export_format == "jsonl":
        emit_human(json.dumps(payload, sort_keys=True))
        return
    if export_format == "md":
        emit_human(_render_markdown(payload))
        return
    raise typer.BadParameter("--format must be jsonl or md")


@app.command("review")
def runs_review(
    run_id: str = typer.Argument(...),
    question: str = typer.Option(
        "What should we polish in this run?",
        "--question",
        help="Taste question to include in the review packet.",
    ),
    fetch_messages: bool = typer.Option(
        True,
        "--fetch-messages/--no-fetch-messages",
        help="Fetch the persisted conversation transcript when the run has a conversation id.",
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Build the compact polish-review packet for one lab run."""
    state = load_state(profile)
    payload = load_run(profile, run_id)
    payload.setdefault("run_path", str(runs_dir(profile) / f"{run_id}.json"))
    packet = asyncio.run(
        _build_review_packet(
            state,
            payload,
            question=question,
            fetch_messages=fetch_messages,
        )
    )
    if json_out:
        emit_json(packet)
        return
    emit_human(str(packet["markdown"]))


def _render_markdown(payload: dict[str, object]) -> str:
    """Render a compact Markdown run report."""
    summary = payload.get("summary")
    lines = [
        f"# Paw Lab Run {payload.get('run_id')}",
        "",
        f"- Kind: {payload.get('kind')}",
        f"- Model: {payload.get('model_id')}",
        f"- Created: {payload.get('created_at')}",
        f"- Summary: `{json.dumps(summary, sort_keys=True)}`",
    ]
    return "\n".join(lines)


async def _build_review_packet(
    state: PersonaState,
    payload: dict[str, Any],
    *,
    question: str,
    fetch_messages: bool,
) -> dict[str, Any]:
    """Return a review packet with run metadata, inputs, transcript, and timing."""
    conversation_id = _conversation_id(payload)
    transcript, transcript_error = await _fetch_transcript(
        state,
        conversation_id,
        fetch_messages=fetch_messages,
    )
    packet = {
        "run_id": payload.get("run_id"),
        "kind": payload.get("kind"),
        "created_at": payload.get("created_at"),
        "model_id": payload.get("model_id"),
        "conversation_id": conversation_id,
        "summary": payload.get("summary") or {},
        "run_path": payload.get("run_path") or "",
        "taste_question": question,
        "telegram_inputs": _telegram_inputs(payload),
        "media": payload.get("media") or {},
        "provider_rows": _provider_rows(payload),
        "persisted_messages": transcript,
        "transcript_fetch_error": transcript_error,
    }
    packet["markdown"] = _render_review_packet(packet)
    return packet


async def _fetch_transcript(
    state: PersonaState,
    conversation_id: str | None,
    *,
    fetch_messages: bool,
) -> tuple[list[dict[str, str]], str]:
    """Fetch persisted messages for the conversation named by a lab run."""
    if not fetch_messages or not conversation_id:
        return [], ""
    try:
        async with PawClient(state) as client:
            response = await client.request(
                "GET",
                f"/api/v1/conversations/{conversation_id}/messages",
                expect=(200,),
            )
    except (OSError, PawError) as exc:
        return [], str(exc)
    body = response.json()
    if not isinstance(body, list):
        return [], "messages response was not a list"
    return [_compact_message(row) for row in body if isinstance(row, dict)], ""


def _compact_message(row: dict[str, Any]) -> dict[str, str]:
    """Return the review-safe subset of a persisted chat message."""
    return {
        "role": str(row.get("role") or ""),
        "content": str(row.get("content") or ""),
        "thinking": str(row.get("thinking") or ""),
        "status": str(row.get("assistant_status") or ""),
    }


def _conversation_id(payload: dict[str, Any]) -> str | None:
    """Return the top-level conversation id for a lab run when available."""
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return None
    conversation_id = summary.get("conversation_id")
    return str(conversation_id) if conversation_id else None


def _telegram_inputs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return compact Telegram input rows from a run payload."""
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []
    return [_telegram_input(row) for row in messages if isinstance(row, dict)]


def _telegram_input(row: dict[str, Any]) -> dict[str, Any]:
    """Return one compact Telegram input row."""
    response = row.get("response") if isinstance(row.get("response"), dict) else {}
    return {
        "index": row.get("index"),
        "text": row.get("text") or "",
        "media": row.get("media") or {},
        "client_duration_ms": row.get("client_duration_ms"),
        "accepted": response.get("accepted") if isinstance(response, dict) else None,
        "conversation_id": response.get("conversation_id") if isinstance(response, dict) else None,
    }


def _provider_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return compact provider-matrix rows for review packets."""
    provider_runs = payload.get("provider_runs")
    if not isinstance(provider_runs, list):
        return []
    return [_provider_row(row) for row in provider_runs if isinstance(row, dict)]


def _provider_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return one compact provider-matrix row."""
    child = row.get("run") if isinstance(row.get("run"), dict) else {}
    summary = child.get("summary") if isinstance(child, dict) else {}
    return {
        "host": row.get("host"),
        "model_id": row.get("model_id"),
        "ok": row.get("ok"),
        "conversation_id": summary.get("conversation_id") if isinstance(summary, dict) else None,
        "max_client_duration_ms": (
            summary.get("max_client_duration_ms") if isinstance(summary, dict) else None
        ),
        "error": row.get("error") or "",
    }


def _render_review_packet(packet: dict[str, Any]) -> str:
    """Render the polish-review packet as Markdown."""
    lines = [
        "# Paw Polish Review",
        "",
        f"- Run: {packet.get('run_id')}",
        f"- Kind: {packet.get('kind')}",
        f"- Model: {packet.get('model_id') or ''}",
        f"- Conversation: {packet.get('conversation_id') or ''}",
        f"- Created: {packet.get('created_at') or ''}",
        f"- Summary: `{json.dumps(packet.get('summary') or {}, sort_keys=True)}`",
    ]
    run_path = packet.get("run_path")
    if run_path:
        lines.append(f"- Run Path: {run_path}")
    lines.extend(["", "## Taste Question", str(packet.get("taste_question") or "")])
    lines.extend(_telegram_inputs_section(packet))
    lines.extend(_media_section(packet))
    lines.extend(_transcript_section(packet))
    lines.extend(_provider_section(packet))
    return "\n".join(lines)


def _telegram_inputs_section(packet: dict[str, Any]) -> list[str]:
    """Render the Telegram input rows in a review packet."""
    rows = packet.get("telegram_inputs")
    if not isinstance(rows, list) or not rows:
        return []
    lines = ["", "## Telegram Inputs"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = _input_label(row)
        duration = row.get("client_duration_ms")
        accepted = row.get("accepted")
        lines.append(f"- [{row.get('index')}] {label} ({duration} ms, accepted={accepted})")
    return lines


def _input_label(row: dict[str, Any]) -> str:
    """Return a compact label for one Telegram input row."""
    text = str(row.get("text") or "").strip()
    media = row.get("media")
    suffix = " + media" if isinstance(media, dict) and media else ""
    return f"{_preview(text, 120)}{suffix}" if text else f"media{suffix}"


def _media_section(packet: dict[str, Any]) -> list[str]:
    """Render media metadata for a review packet."""
    media = packet.get("media")
    if not isinstance(media, dict) or not media:
        return []
    return ["", "## Media", f"```json\n{json.dumps(media, indent=2, sort_keys=True)}\n```"]


def _transcript_section(packet: dict[str, Any]) -> list[str]:
    """Render persisted conversation messages for a review packet."""
    rows = packet.get("persisted_messages")
    if not isinstance(rows, list) or not rows:
        error = str(packet.get("transcript_fetch_error") or "")
        detail = (
            f"No persisted transcript fetched. {error}"
            if error
            else "No persisted transcript fetched."
        )
        return ["", "## Persisted Conversation", detail]
    lines = ["", "## Persisted Conversation"]
    for index, row in enumerate(rows):
        if isinstance(row, dict):
            lines.append(_message_line(index, row))
    return lines


def _message_line(index: int, row: dict[str, Any]) -> str:
    """Render one persisted message as a compact Markdown bullet."""
    role = str(row.get("role") or "message")
    content = _preview(str(row.get("content") or ""), 300)
    thinking = _preview(str(row.get("thinking") or ""), 160)
    suffix = f" Thinking: {thinking}" if thinking else ""
    return f"- [{index}] {role}: {content}{suffix}"


def _provider_section(packet: dict[str, Any]) -> list[str]:
    """Render provider-matrix rows for a review packet."""
    rows = packet.get("provider_rows")
    if not isinstance(rows, list) or not rows:
        return []
    lines = ["", "## Provider Matrix"]
    lines.extend(_provider_line(row) for row in rows if isinstance(row, dict))
    return lines


def _provider_line(row: dict[str, Any]) -> str:
    """Render one provider-matrix row."""
    status = "ok" if row.get("ok") else "failed"
    duration = row.get("max_client_duration_ms")
    error = f" error={row.get('error')}" if row.get("error") else ""
    return (
        f"- {row.get('host')}: {status}, model={row.get('model_id')}, "
        f"conversation={row.get('conversation_id')}, max_client_duration_ms={duration}{error}"
    )


def _preview(value: str, limit: int) -> str:
    """Return a single-line preview capped at ``limit`` characters."""
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."
