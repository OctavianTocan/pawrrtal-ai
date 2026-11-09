"""paw appearance — user appearance settings."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, cast

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json

COLOR_ROLES = ("background", "foreground", "accent", "info", "success", "destructive")
PALETTES = ("light", "dark")
THEME_MODES = ("light", "dark", "system")

app = typer.Typer(
    help="Read, update, or reset appearance settings.",
    no_args_is_help=True,
)


@app.command("get")
def appearance_get(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Fetch the authenticated user's appearance settings."""
    state = load_state(profile)
    payload = asyncio.run(_get_appearance(state))
    if json_out:
        emit_json(payload)
        return
    _emit_appearance(payload)


@app.command("set")
def appearance_set(
    palette: str = typer.Option("light", "--palette", help="Palette for color roles: light|dark."),
    background: str | None = typer.Option(None, "--background"),
    foreground: str | None = typer.Option(None, "--foreground"),
    accent: str | None = typer.Option(None, "--accent"),
    info: str | None = typer.Option(None, "--info"),
    success: str | None = typer.Option(None, "--success"),
    destructive: str | None = typer.Option(None, "--destructive"),
    theme_mode: str | None = typer.Option(None, "--theme-mode", help="light|dark|system."),
    font_display: str | None = typer.Option(None, "--font-display"),
    font_sans: str | None = typer.Option(None, "--font-sans"),
    font_mono: str | None = typer.Option(None, "--font-mono"),
    ui_font_size: int | None = typer.Option(None, "--ui-font-size"),
    pointer_cursors: bool | None = typer.Option(
        None,
        "--pointer-cursors/--no-pointer-cursors",
        help="Toggle pointer cursors for interactive UI.",
    ),
    translucent_sidebar: bool | None = typer.Option(
        None,
        "--translucent-sidebar/--solid-sidebar",
        help="Toggle translucent sidebar styling.",
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Merge targeted appearance updates and save the full settings object."""
    state = load_state(profile)
    payload = asyncio.run(
        _merge_appearance_updates(
            state,
            palette=palette,
            colors={
                "background": background,
                "foreground": foreground,
                "accent": accent,
                "info": info,
                "success": success,
                "destructive": destructive,
            },
            theme_mode=theme_mode,
            fonts={
                "display": font_display,
                "sans": font_sans,
                "mono": font_mono,
            },
            options={
                "ui_font_size": ui_font_size,
                "pointer_cursors": pointer_cursors,
                "translucent_sidebar": translucent_sidebar,
            },
        )
    )
    if json_out:
        emit_json(payload)
        return
    _emit_appearance(payload)


@app.command("reset")
def appearance_reset(
    yes: bool = typer.Option(False, "--yes", "-y"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Reset appearance settings back to frontend defaults."""
    if not yes:
        raise LocalError(
            "Pass --yes to confirm reset.",
            hint="paw appearance reset --yes",
        )
    state = load_state(profile)
    result = asyncio.run(_reset_appearance(state))
    if json_out:
        emit_json(result)
        return
    emit_human("appearance reset")


def _emit_appearance(payload: dict[str, Any]) -> None:
    """Compact human output for appearance settings."""
    options = _as_dict(payload.get("options"))
    fonts = _as_dict(payload.get("fonts"))
    light = _as_dict(payload.get("light"))
    dark = _as_dict(payload.get("dark"))
    emit_human(
        f"theme: {options.get('theme_mode') or 'system'}\n"
        f"accent: light={light.get('accent') or '-'} dark={dark.get('accent') or '-'}\n"
        f"font: {fonts.get('sans') or '-'}"
    )


async def _get_appearance(state: PersonaState) -> dict[str, Any]:
    """GET /api/v1/appearance."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/api/v1/appearance", expect=(200,))
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def _put_appearance(state: PersonaState, payload: dict[str, Any]) -> dict[str, Any]:
    """PUT /api/v1/appearance."""
    async with PawClient(state) as client:
        resp = await client.request(
            "PUT",
            "/api/v1/appearance",
            json_body=payload,
            expect=(200,),
        )
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def _reset_appearance(state: PersonaState) -> dict[str, Any]:
    """DELETE /api/v1/appearance."""
    async with PawClient(state) as client:
        await client.request("DELETE", "/api/v1/appearance", expect=(204,))
    return {"reset": True}


async def _merge_appearance_updates(
    state: PersonaState,
    *,
    palette: str,
    colors: dict[str, str | None],
    theme_mode: str | None,
    fonts: dict[str, str | None],
    options: dict[str, int | bool | None],
) -> dict[str, Any]:
    """Read, merge provided appearance fields, and PUT the full payload."""
    palette = palette.lower()
    if palette not in PALETTES:
        raise LocalError("Bad --palette value.", hint="Use --palette light or --palette dark.")
    if theme_mode is not None and theme_mode not in THEME_MODES:
        raise LocalError("Bad --theme-mode value.", hint="Use light, dark, or system.")
    current = await _get_appearance(state)
    changed = _merge_color_updates(current, palette, colors)
    changed += _merge_section_updates(current, "fonts", fonts)
    changed += _merge_section_updates(current, "options", options)
    if theme_mode is not None:
        options_payload = _section(current, "options")
        options_payload["theme_mode"] = theme_mode
        changed += 1
    if changed == 0:
        raise LocalError(
            "No appearance fields provided.",
            hint="Use `paw appearance set --accent '#7c5cff'` or another field option.",
        )
    return await _put_appearance(state, current)


def _merge_color_updates(
    payload: dict[str, Any],
    palette: str,
    colors: dict[str, str | None],
) -> int:
    """Merge provided color roles into one palette."""
    target = _section(payload, palette)
    changed = 0
    for role in COLOR_ROLES:
        value = colors.get(role)
        if value is not None:
            target[role] = value
            changed += 1
    return changed


def _merge_section_updates(
    payload: dict[str, Any],
    section_name: str,
    values: Mapping[str, str | int | bool | None],
) -> int:
    """Merge provided scalar values into a nested section."""
    target = _section(payload, section_name)
    changed = 0
    for key, value in values.items():
        if value is not None:
            target[key] = value
            changed += 1
    return changed


def _section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a mutable nested dict, creating it when needed."""
    current = payload.get(key)
    if isinstance(current, dict):
        return cast("dict[str, Any]", current)
    section: dict[str, Any] = {}
    payload[key] = section
    return section


def _as_dict(value: Any) -> dict[str, Any]:
    """Coerce an arbitrary value to a dict for display."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}
