"""Telegram dogfood commands for ``paw lab``."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from app.cli.paw.config import load_state
from app.cli.paw.output import emit_human, emit_json

from .storage import write_run
from .telegram_runtime import (
    raise_on_provider_failures,
    render_telegram_chat,
    render_telegram_providers,
    telegram_chat_payload,
    telegram_media_payload,
    telegram_providers_payload,
)

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
        telegram_chat_payload(
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
    emit_human(render_telegram_chat(payload))


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
        telegram_media_payload(
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
    emit_human(render_telegram_chat(payload))


@app.command("providers")
def telegram_providers(
    text: str = typer.Option("", "--text", help="Caption/text for each media turn."),
    image: Path | None = typer.Option(None, "--image", help="Image file to attach."),
    voice_note: Path | None = typer.Option(None, "--voice-note", help="Voice-note audio file."),
    voice_duration: int = typer.Option(1, "--voice-duration", min=0, max=3600),
    include_host: list[str] = typer.Option(
        [],
        "--host",
        help="Provider host to include. Repeatable. Default: every authenticated host.",
    ),
    verbose_level: int | None = typer.Option(None, "--verbose", min=0, max=2),
    timeout: float = typer.Option(DEFAULT_TELEGRAM_TIMEOUT_SECONDS, "--timeout", min=1.0),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Send the same Telegram media turn through one model per provider host."""
    state = load_state(profile)
    payload = asyncio.run(
        telegram_providers_payload(
            state,
            text=text,
            image_path=image,
            voice_note_path=voice_note,
            voice_duration=voice_duration,
            include_hosts=set(include_host),
            verbose_level=verbose_level,
            request_timeout=timeout,
        )
    )
    path = write_run(profile, payload)
    payload["run_path"] = str(path)
    if json_out:
        emit_json(payload)
        raise_on_provider_failures(payload)
        return
    emit_human(render_telegram_providers(payload))
    raise_on_provider_failures(payload)
