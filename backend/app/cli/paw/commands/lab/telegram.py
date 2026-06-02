"""Telegram dogfood commands for ``paw lab``."""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import time
from pathlib import Path
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json

from .storage import new_run_id, write_run

DEFAULT_TELEGRAM_TIMEOUT_SECONDS = 240.0

app = typer.Typer(help="Drive Telegram simulation flows.", no_args_is_help=True)


@app.command("chat")
def telegram_chat(
    model: str = typer.Option(..., "--model", help="Model id to select through /model."),
    turns: Path = typer.Option(..., "--turns", help="Text file containing one turn per line."),
    new: bool = typer.Option(False, "--new", help="Start a fresh Telegram conversation first."),
    verbose_level: int | None = typer.Option(None, "--verbose", min=0, max=2),
    timeout: float = typer.Option(DEFAULT_TELEGRAM_TIMEOUT_SECONDS, "--timeout", min=1.0),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Send a scripted Telegram chat through the dev-only simulate endpoint."""
    state = load_state(profile)
    payload = asyncio.run(
        _telegram_chat_payload(
            state,
            model_id=model,
            turns_path=turns,
            new=new,
            verbose_level=verbose_level,
            request_timeout=timeout,
        )
    )
    path = write_run(profile, payload)
    payload["run_path"] = str(path)
    if json_out:
        emit_json(payload)
        return
    emit_human(_render_telegram_chat(payload))


@app.command("media")
def telegram_media(
    model: str = typer.Option(..., "--model", help="Model id to select through /model."),
    text: str = typer.Option("", "--text", help="Caption/text for the media turn."),
    image: Path | None = typer.Option(None, "--image", help="Image file to attach."),
    voice_note: Path | None = typer.Option(None, "--voice-note", help="Voice-note audio file."),
    voice_duration: int = typer.Option(1, "--voice-duration", min=0, max=3600),
    new: bool = typer.Option(False, "--new", help="Start a fresh Telegram conversation first."),
    verbose_level: int | None = typer.Option(None, "--verbose", min=0, max=2),
    timeout: float = typer.Option(DEFAULT_TELEGRAM_TIMEOUT_SECONDS, "--timeout", min=1.0),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Send one Telegram simulation turn with image and/or voice-note media."""
    state = load_state(profile)
    payload = asyncio.run(
        _telegram_media_payload(
            state,
            model_id=model,
            text=text,
            image_path=image,
            voice_note_path=voice_note,
            voice_duration=voice_duration,
            new=new,
            verbose_level=verbose_level,
            request_timeout=timeout,
        )
    )
    path = write_run(profile, payload)
    payload["run_path"] = str(path)
    if json_out:
        emit_json(payload)
        return
    emit_human(_render_telegram_chat(payload))


async def _telegram_chat_payload(
    state: PersonaState,
    *,
    model_id: str,
    turns_path: Path,
    new: bool,
    verbose_level: int | None,
    request_timeout: float,
) -> dict[str, Any]:
    """Build and run a Telegram simulation script."""
    messages = _script_messages(
        model_id=model_id,
        turns=_read_turns(turns_path),
        new=new,
        verbose_level=verbose_level,
    )
    entries: list[dict[str, Any]] = []
    async with PawClient(state, timeout=request_timeout) as client:
        for index, text in enumerate(messages):
            entries.append(await _send_simulated_message(client, index=index, text=text))
    return {
        "run_id": new_run_id("telegram-chat"),
        "kind": "telegram-chat",
        "model_id": model_id,
        "turns_path": str(turns_path),
        "messages": entries,
        "summary": {
            "messages_sent": len(entries),
            "conversation_id": _latest_conversation_id(entries),
            "max_client_duration_ms": _max_duration(entries),
        },
    }


async def _telegram_media_payload(
    state: PersonaState,
    *,
    model_id: str,
    text: str,
    image_path: Path | None,
    voice_note_path: Path | None,
    voice_duration: int,
    new: bool,
    verbose_level: int | None,
    request_timeout: float,
) -> dict[str, Any]:
    """Build and run a Telegram media simulation turn."""
    media_payload = _build_media_payload(
        text=text,
        image_path=image_path,
        voice_note_path=voice_note_path,
        voice_duration=voice_duration,
    )
    control_messages = _script_messages(
        model_id=model_id,
        turns=[],
        new=new,
        verbose_level=verbose_level,
    )
    entries: list[dict[str, Any]] = []
    async with PawClient(state, timeout=request_timeout) as client:
        for index, control_text in enumerate(control_messages):
            entries.append(await _send_simulated_message(client, index=index, text=control_text))
        entries.append(
            await _send_simulated_payload(
                client,
                index=len(entries),
                payload=media_payload,
            )
        )
    return {
        "run_id": new_run_id("telegram-media"),
        "kind": "telegram-media",
        "model_id": model_id,
        "media": _media_summary(media_payload),
        "messages": entries,
        "summary": {
            "messages_sent": len(entries),
            "conversation_id": _latest_conversation_id(entries),
            "max_client_duration_ms": _max_duration(entries),
        },
    }


def _read_turns(path: Path) -> list[str]:
    """Read non-empty, non-comment turns from a text file."""
    if not path.exists():
        raise LocalError(f"Turn file does not exist: {path}")
    rows = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not rows:
        raise LocalError(f"Turn file has no usable turns: {path}")
    return rows


def _script_messages(
    *,
    model_id: str,
    turns: list[str],
    new: bool,
    verbose_level: int | None,
) -> list[str]:
    """Return control messages followed by scenario turns."""
    messages: list[str] = []
    if new:
        messages.append("/new")
    messages.append(f"/model {model_id}")
    if verbose_level is not None:
        messages.append(f"/verbose {verbose_level}")
    messages.extend(turns)
    return messages


async def _send_simulated_message(
    client: PawClient,
    *,
    index: int,
    text: str,
) -> dict[str, Any]:
    """POST one synthetic Telegram message and return a run-log entry."""
    started = time.perf_counter()
    response = await client.request(
        "POST",
        "/api/v1/channels/telegram/simulate",
        json_body={"text": text},
        expect=(200,),
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    body = response.json()
    if not isinstance(body, dict):
        raise LocalError("Telegram simulate endpoint returned a non-object response.")
    return {
        "index": index,
        "text": text,
        "client_duration_ms": duration_ms,
        "response": body,
    }


async def _send_simulated_payload(
    client: PawClient,
    *,
    index: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """POST one synthetic Telegram payload and return a run-log entry."""
    started = time.perf_counter()
    response = await client.request(
        "POST",
        "/api/v1/channels/telegram/simulate",
        json_body=payload,
        expect=(200,),
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    body = response.json()
    if not isinstance(body, dict):
        raise LocalError("Telegram simulate endpoint returned a non-object response.")
    return {
        "index": index,
        "text": payload.get("text") or "",
        "media": _media_summary(payload),
        "client_duration_ms": duration_ms,
        "response": body,
    }


def _build_media_payload(
    *,
    text: str,
    image_path: Path | None,
    voice_note_path: Path | None,
    voice_duration: int,
) -> dict[str, Any]:
    """Return the simulate-route JSON payload for one media turn."""
    if image_path is None and voice_note_path is None:
        raise LocalError("Provide --image, --voice-note, or both.")
    payload: dict[str, Any] = {}
    if text.strip():
        payload["text"] = text.strip()
    if image_path is not None:
        payload["image"] = _encoded_file_payload(
            image_path,
            default_mime="image/jpeg",
            allowed_mime_types=("image/jpeg",),
            label="image",
        )
    if voice_note_path is not None:
        voice_payload = _encoded_file_payload(
            voice_note_path,
            default_mime="audio/ogg",
            allowed_prefix="audio/",
            label="voice note",
        )
        payload["voice_note"] = {
            "data": voice_payload["data"],
            "mime_type": voice_payload["media_type"],
            "duration_seconds": voice_duration,
        }
    return payload


def _encoded_file_payload(
    path: Path,
    *,
    default_mime: str,
    allowed_prefix: str | None = None,
    allowed_mime_types: tuple[str, ...] | None = None,
    label: str,
) -> dict[str, str]:
    """Read a media file into the simulate-route base64 envelope."""
    if not path.exists():
        raise LocalError(f"{label.capitalize()} file does not exist: {path}")
    if not path.is_file():
        raise LocalError(f"{label.capitalize()} path is not a file: {path}")
    mime_type = mimetypes.guess_type(path.name)[0] or default_mime
    if allowed_mime_types is not None and mime_type not in allowed_mime_types:
        allowed = ", ".join(allowed_mime_types)
        raise LocalError(
            f"{label.capitalize()} file has unsupported MIME type: {mime_type}. Expected {allowed}."
        )
    if allowed_prefix is not None and not mime_type.startswith(allowed_prefix):
        raise LocalError(f"{label.capitalize()} file has unsupported MIME type: {mime_type}")
    return {
        "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        "media_type": mime_type,
    }


def _media_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a compact media summary without embedding base64 bytes."""
    summary: dict[str, Any] = {}
    image = payload.get("image")
    if isinstance(image, dict):
        summary["image"] = {"media_type": image.get("media_type")}
    voice_note = payload.get("voice_note")
    if isinstance(voice_note, dict):
        summary["voice_note"] = {
            "mime_type": voice_note.get("mime_type"),
            "duration_seconds": voice_note.get("duration_seconds"),
        }
    return summary


def _latest_conversation_id(entries: list[dict[str, Any]]) -> str | None:
    """Return the latest conversation id observed in simulate responses."""
    for entry in reversed(entries):
        response = entry.get("response")
        if isinstance(response, dict) and response.get("conversation_id"):
            return str(response["conversation_id"])
    return None


def _max_duration(entries: list[dict[str, Any]]) -> int | None:
    """Return the slowest client-side simulate POST duration."""
    durations = [entry.get("client_duration_ms") for entry in entries]
    numeric = [value for value in durations if isinstance(value, int)]
    return max(numeric) if numeric else None


def _render_telegram_chat(payload: dict[str, Any]) -> str:
    """Render a compact human-readable Telegram lab report."""
    summary = payload.get("summary") or {}
    return (
        f"run_id: {payload.get('run_id')}\n"
        f"model_id: {payload.get('model_id')}\n"
        f"messages_sent: {summary.get('messages_sent')}\n"
        f"conversation_id: {summary.get('conversation_id') or ''}\n"
        f"max_client_duration_ms: {summary.get('max_client_duration_ms')}"
    )
