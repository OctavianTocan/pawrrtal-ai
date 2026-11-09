"""paw profile — personalization profile commands."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json

app = typer.Typer(
    help="Read and update the user's personalization profile.",
    no_args_is_help=True,
)


@app.command("get")
def profile_get(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Fetch the personalization profile used by onboarding and prompts."""
    state = load_state(profile)
    payload = asyncio.run(_get_profile(state))
    if json_out:
        emit_json(payload)
        return
    _emit_profile(payload)


@app.command("set")
def profile_set(
    name: str | None = typer.Option(None, "--name"),
    role: str | None = typer.Option(None, "--role"),
    company_website: str | None = typer.Option(None, "--company-website"),
    linkedin: str | None = typer.Option(None, "--linkedin"),
    goal: list[str] = typer.Option([], "--goal", help="Repeatable goal entry."),
    connected_channel: list[str] = typer.Option(
        [], "--connected-channel", help="Repeatable connected channel name."
    ),
    chatgpt_context: str | None = typer.Option(None, "--chatgpt-context"),
    personality: str | None = typer.Option(None, "--personality"),
    custom_instructions: str | None = typer.Option(None, "--custom-instructions"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Merge updates into the personalization profile.

    The backend treats PUT as a full replacement, so the CLI first reads the
    existing profile and only changes the fields provided on this command.
    """
    state = load_state(profile)
    payload = asyncio.run(
        _merge_profile_updates(
            state,
            name=name,
            role=role,
            company_website=company_website,
            linkedin=linkedin,
            goals=goal,
            connected_channels=connected_channel,
            chatgpt_context=chatgpt_context,
            personality=personality,
            custom_instructions=custom_instructions,
        )
    )
    if json_out:
        emit_json(payload)
        return
    _emit_profile(payload)


def _emit_profile(payload: dict[str, Any]) -> None:
    """Compact profile summary for human output."""
    goals = payload.get("goals") or []
    channels = payload.get("connected_channels") or []
    emit_human(
        f"name: {payload.get('name') or '-'}\n"
        f"role: {payload.get('role') or '-'}\n"
        f"goals: {len(goals) if isinstance(goals, list) else 0}\n"
        f"channels: {len(channels) if isinstance(channels, list) else 0}"
    )


async def _get_profile(state: PersonaState) -> dict[str, Any]:
    """GET /api/v1/personalization."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/api/v1/personalization", expect=(200,))
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def _put_profile(state: PersonaState, payload: dict[str, Any]) -> dict[str, Any]:
    """PUT /api/v1/personalization."""
    async with PawClient(state) as client:
        resp = await client.request(
            "PUT",
            "/api/v1/personalization",
            json_body=payload,
            expect=(200,),
        )
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def _merge_profile_updates(
    state: PersonaState,
    *,
    name: str | None,
    role: str | None,
    company_website: str | None,
    linkedin: str | None,
    goals: list[str],
    connected_channels: list[str],
    chatgpt_context: str | None,
    personality: str | None,
    custom_instructions: str | None,
) -> dict[str, Any]:
    """Read, merge provided fields, and PUT the full profile."""
    updates: dict[str, Any] = {}
    _add_optional(updates, "name", name)
    _add_optional(updates, "role", role)
    _add_optional(updates, "company_website", company_website)
    _add_optional(updates, "linkedin", linkedin)
    _add_optional(updates, "chatgpt_context", chatgpt_context)
    _add_optional(updates, "personality", personality)
    _add_optional(updates, "custom_instructions", custom_instructions)
    if goals:
        updates["goals"] = goals
    if connected_channels:
        updates["connected_channels"] = connected_channels
    if not updates:
        raise LocalError(
            "No profile fields provided.",
            hint="Use `paw profile set --name ...` or another field option.",
        )
    current = await _get_profile(state)
    current.update(updates)
    return await _put_profile(state, current)


def _add_optional(updates: dict[str, Any], key: str, value: str | None) -> None:
    """Add an optional scalar update when the CLI flag was provided."""
    if value is not None:
        updates[key] = value
