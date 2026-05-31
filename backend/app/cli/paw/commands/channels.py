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
from typing import Any, cast

import httpx
import typer
from sqlalchemy import select

from app.cli.paw.commands.channel_diagnostics import diagnose_telegram_state as _diagnose_telegram
from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User, async_session_maker
from app.infrastructure.models.channel import ChannelBinding

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
TELEGRAM_SEND_OK_STATUS = 200

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
send_app = typer.Typer(
    help="Send an operator test message through a channel.",
    no_args_is_help=True,
)

app.add_typer(link_app, name="link")
app.add_typer(unlink_app, name="unlink")
app.add_typer(send_app, name="send")


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


@send_app.command("telegram")
def send_telegram(
    text: str = typer.Option(..., "--text", help="Text to send."),
    chat_id: str | None = typer.Option(None, "--chat-id", help="Telegram chat id."),
    user_email: str | None = typer.Option(
        None,
        "--user-email",
        help="Resolve the Telegram chat id from this local Pawrrtal user.",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Send a trusted local operator test message via the configured bot token.

    Exactly one of ``--chat-id`` or ``--user-email`` is required. This bypasses
    the public HTTP API because it is meant for local setup verification before
    a user can drive the normal Telegram bot flow.
    """
    if bool(chat_id) == bool(user_email):
        raise LocalError("Specify exactly one of --chat-id or --user-email.")
    result = asyncio.run(_send_telegram(chat_id=chat_id, user_email=user_email, text=text))
    if json_out:
        emit_json(result)
        return
    emit_human(
        f"sent telegram message.\n"
        f"  chat_id:    {result.get('chat_id')}\n"
        f"  message_id: {result.get('message_id')}"
    )


@app.command("diagnose-telegram")
def diagnose_telegram(
    limit: int = typer.Option(10, "--limit", min=1, max=50),
    conversation_id: str | None = typer.Option(
        None,
        "--conversation-id",
        help="Include a focused trace for one Telegram/Pawrrtal conversation.",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Inspect local Telegram binding and recent persisted turn state."""
    payload = asyncio.run(_diagnose_telegram(limit=limit, conversation_id=conversation_id))
    if json_out:
        emit_json(payload)
        return
    lines = [
        f"telegram_configured: {payload['configured']}",
        f"telegram_mode: {payload['mode']}",
        f"bindings: {len(payload['bindings'])}",
        f"recent_messages: {len(payload['recent_messages'])}",
        f"stuck_streaming_messages: {len(payload['stuck_streaming_messages'])}",
    ]
    lines.extend(
        (
            "stuck\t"
            f"{message['created_at']}\t"
            f"conversation={message['conversation_id']}\t"
            f"ordinal={message['ordinal']}\t"
            f"model={message['model_id'] or ''}"
        )
        for message in payload["stuck_streaming_messages"]
    )
    if payload.get("conversation_trace"):
        trace = payload["conversation_trace"]
        lines.extend(
            [
                "conversation_trace:",
                f"  id: {trace['conversation_id']}",
                f"  model_id: {trace['model_id'] or ''}",
                f"  codex_thread_id: {trace['codex_thread_id'] or ''}",
                f"  skill_prompt_mode: {trace.get('workspace_skill_prompt_mode') or ''}",
                f"  message_count: {len(trace['messages'])}",
                f"  usage_rows: {len(trace.get('recent_usage') or [])}",
            ]
        )
        lines.extend(
            (
                "  usage\t"
                f"{usage['created_at']}\t"
                f"in={usage['input_tokens']}\t"
                f"out={usage['output_tokens']}\t"
                f"cost={usage['cost_usd']:.6f}\t"
                f"model={usage['model_id']}"
            )
            for usage in trace.get("recent_usage") or []
        )
        lines.extend(
            (
                "  message\t"
                f"{message['created_at']}\t"
                f"ordinal={message['ordinal']}\t"
                f"role={message['role']}\t"
                f"status={message['assistant_status'] or ''}\t"
                f"duration_ms={message['duration_ms'] or ''}\t"
                f"timeline={message['timeline_count']}\t"
                f"thinking_chars={message['thinking_chars']}\t"
                f"content={message['content_preview']}"
            )
            for message in trace["messages"]
        )
    emit_human("\n".join(lines))


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


async def _send_telegram(
    *,
    chat_id: str | None,
    user_email: str | None,
    text: str,
) -> dict[str, Any]:
    """Send a Telegram message through the configured bot token."""
    token = settings.telegram_bot_token
    if not token:
        raise LocalError("TELEGRAM_BOT_TOKEN is not configured.")
    resolved_chat_id = chat_id or await _telegram_chat_id_for_email(user_email or "")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            url,
            json={"chat_id": resolved_chat_id, "text": text},
        )
    if response.status_code != TELEGRAM_SEND_OK_STATUS:
        raise LocalError(
            "Telegram sendMessage failed.",
            hint=f"status={response.status_code} body={response.text[:200]}",
        )
    body = response.json()
    result = body.get("result") if isinstance(body, dict) else None
    if not isinstance(result, dict):
        raise LocalError("Telegram sendMessage returned an unexpected response.")
    return {
        "ok": True,
        "chat_id": str(result.get("chat", {}).get("id", resolved_chat_id)),
        "message_id": result.get("message_id"),
    }


async def _telegram_chat_id_for_email(email: str) -> str:
    """Resolve a local user's Telegram chat id from the configured database."""
    user_model = cast(Any, User)
    async with async_session_maker() as session:
        result = await session.execute(
            select(ChannelBinding.external_chat_id)
            .join(User, user_model.id == ChannelBinding.user_id)
            .where(user_model.email == email, ChannelBinding.provider == TELEGRAM_PROVIDER)
            .limit(1)
        )
        chat_id = result.scalar_one_or_none()
    if not chat_id:
        raise LocalError(f"No Telegram binding found for user email {email}.")
    return str(chat_id)
