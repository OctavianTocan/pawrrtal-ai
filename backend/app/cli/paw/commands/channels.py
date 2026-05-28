"""paw channels — third-party messaging channel link/unlink.

Drives the same backend surface as the Settings UI's Telegram card
(``/api/v1/channels`` family). The backend is provider-keyed: bindings
do not expose a per-row UUID. ``ChannelBindingRead`` carries
``provider`` + ``external_user_id`` + ``display_handle``; the
unlink endpoint is path-scoped per provider
(``DELETE /api/v1/channels/telegram/link``).

Verbs:

- ``paw channels list``         GET /api/v1/channels
- ``paw channels link telegram`` POST /api/v1/channels/telegram/link
                                  — issues a one-time code the user
                                    pastes into the Telegram bot.
- ``paw channels unlink telegram`` DELETE /api/v1/channels/telegram/link
                                    — idempotent; 204 even when nothing
                                      was bound.

Not implemented: ``simulate-update``. The closest backend surface
(``POST /api/v1/channels/telegram/webhook``) accepts only real
Telegram update payloads, requires the ``X-Telegram-Bot-Api-Secret-Token``
header to match the deployment secret, and 404s outside webhook mode.
A simulate endpoint can be added later as ``POST /api/v1/channels/{provider}/simulate``
and wired here without churning the verb surface.

Output modes mirror ``paw conversations`` / ``paw workspaces``:
``--json``, ``--plain``, default human-readable. Exit codes come from
``app.cli.paw.errors``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

# Column widths for `paw channels list` on an 80-col terminal: 12-char
# provider, 30-char external user id (Telegram numeric IDs fit easily),
# remainder for the @handle.
LS_PROVIDER_WIDTH = 12
LS_EXTERNAL_ID_WIDTH = 30
LS_HANDLE_WIDTH = 24

# Canonical provider name. Listed once so a future Slack/iMessage
# provider lands as a sibling Typer subcommand, not a string literal
# scattered across helpers.
TELEGRAM_PROVIDER = "telegram"

app = typer.Typer(
    help="Manage third-party messaging channel bindings (Telegram link / unlink).",
    no_args_is_help=True,
)

link_app = typer.Typer(
    help="Issue a one-time code to bind a channel to the persona.",
    no_args_is_help=True,
)

unlink_app = typer.Typer(
    help="Drop an existing channel binding (idempotent).",
    no_args_is_help=True,
)

app.add_typer(link_app, name="link")
app.add_typer(unlink_app, name="unlink")


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# paw channels list / ls
# --------------------------------------------------------------------------- #


@app.command("list")
def channels_list(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List every channel binding the authenticated persona currently owns.

    Bindings have no per-row UUID — the backend keys them by ``(user_id,
    provider)``. ``paw channels unlink <provider>`` uses the provider
    string (today: ``telegram``) as the identifier.

    Examples:
      paw channels list
      paw channels list --json
      paw channels list --plain
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    state = load_state(profile)
    bindings = asyncio.run(_list_channels(state))

    if json_out:
        emit_json(bindings)
        return
    if plain:
        emit_plain_rows(
            (
                b.get("provider"),
                b.get("external_user_id"),
                b.get("display_handle") or "",
                b.get("created_at") or "",
            )
            for b in bindings
        )
        return

    header = (
        f"{'PROVIDER':<{LS_PROVIDER_WIDTH}}  "
        f"{'EXTERNAL_USER_ID':<{LS_EXTERNAL_ID_WIDTH}}  "
        f"{'HANDLE':<{LS_HANDLE_WIDTH}}  CREATED"
    )
    emit_human(header)
    for binding in bindings:
        provider = str(binding.get("provider", ""))[:LS_PROVIDER_WIDTH]
        external_user_id = str(binding.get("external_user_id", ""))[:LS_EXTERNAL_ID_WIDTH]
        handle = str(binding.get("display_handle") or "")[:LS_HANDLE_WIDTH]
        emit_human(
            f"{provider:<{LS_PROVIDER_WIDTH}}  "
            f"{external_user_id:<{LS_EXTERNAL_ID_WIDTH}}  "
            f"{handle:<{LS_HANDLE_WIDTH}}  "
            f"{binding.get('created_at', '')}"
        )


# `ls` alias for muscle memory with the other paw resources.
app.command("ls", help="Alias for `list`.")(channels_list)


# --------------------------------------------------------------------------- #
# paw channels link telegram
# --------------------------------------------------------------------------- #


@link_app.command("telegram")
def link_telegram(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Issue a fresh one-time code the user pastes into the Telegram bot.

    The backend returns the plaintext code exactly once (DB stores only
    the HMAC). The response also carries ``expires_at``, the bot
    username, and a ``t.me/<bot>?start=<code>`` deep link when the
    deployment has Telegram configured.

    The CLI does *not* consume the code itself — codes are redeemed by
    the user inside the Telegram bot. ``paw channels link telegram``
    is the issue-side; the redeem-side lives in the bot adapter.

    Exit 5 (ApiError) when Telegram is not configured on the backend
    (the route returns 503).

    Examples:
      paw channels link telegram
      paw channels link telegram --json
    """
    state = load_state(profile)
    code = asyncio.run(_issue_telegram_link_code(state))

    if json_out:
        emit_json(code)
        return
    bot_username = code.get("bot_username") or "<unset>"
    deep_link = code.get("deep_link") or "<unavailable — bot_username not configured>"
    emit_human(
        f"code:        {code.get('code')}\n"
        f"expires_at:  {code.get('expires_at')}\n"
        f"bot:         @{bot_username}\n"
        f"deep_link:   {deep_link}"
    )


# --------------------------------------------------------------------------- #
# paw channels unlink telegram
# --------------------------------------------------------------------------- #


@unlink_app.command("telegram")
def unlink_telegram(
    yes: bool = typer.Option(False, "--yes", "-y"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Drop the persona's Telegram binding. Idempotent on already-unbound.

    The backend deliberately returns 204 whether or not a binding
    existed (so the Settings UI can hit "Disconnect" without
    pre-checking state). ``paw`` exposes the same semantics: exit 0
    in both cases.

    Examples:
      paw channels unlink telegram --yes
      paw channels unlink telegram --yes --json
    """
    if not yes:
        raise LocalError(
            "Pass --yes to confirm unlink.",
            hint="paw channels unlink telegram --yes",
        )
    state = load_state(profile)
    result = asyncio.run(_unlink_provider(state, TELEGRAM_PROVIDER))
    if json_out:
        emit_json(result)
        return
    emit_human(f"unlinked {TELEGRAM_PROVIDER}")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #


async def _list_channels(state: PersonaState) -> list[dict[str, Any]]:
    """GET /api/v1/channels; backend returns a bare list of bindings."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/api/v1/channels", expect=(200,))
    body = resp.json()
    if not isinstance(body, list):
        return []
    return [b for b in body if isinstance(b, dict)]


async def _issue_telegram_link_code(state: PersonaState) -> dict[str, Any]:
    """POST /api/v1/channels/telegram/link -> TelegramLinkCodeRead envelope."""
    async with PawClient(state) as client:
        resp = await client.request(
            "POST",
            "/api/v1/channels/telegram/link",
            expect=(200, 201),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _unlink_provider(state: PersonaState, provider: str) -> dict[str, Any]:
    """DELETE /api/v1/channels/{provider}/link; idempotent 204."""
    async with PawClient(state) as client:
        await client.request(
            "DELETE",
            f"/api/v1/channels/{provider}/link",
            expect=(204,),
        )
    return {"unlinked": True, "provider": provider}
