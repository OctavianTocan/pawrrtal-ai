"""Inbound transport + turn driver for the Google Chat channel.

Mirrors :mod:`app.channels.telegram.bot`: a lifespan-managed background
task receives events and drives one ``run_turn`` per inbound message.
Where Telegram long-polls the Bot API, Google Chat events arrive on a
Pub/Sub subscription that we *pull* — so the app needs no public webhook.

Flow per message::

    Pub/Sub pull → decode event → resolve user (dev-admin) →
    get/create conversation → create placeholder message →
    run_turn (provider-agnostic) → GoogleChatChannel.deliver patches it
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import build_agent_tools
from app.channels.base import ChannelMessage
from app.channels.turn_runner import ChatTurnInput, run_turn
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import async_session_maker
from app.models import Conversation
from app.providers.base import AILLM
from app.providers.catalog import default_model
from app.providers.factory import resolve_llm
from app.providers.model_id import InvalidModelId, UnknownModelId
from app.workspace.crud import get_default_workspace

from .attachments import collect_attachments
from .auth import has_google_chat_auth
from .cards import apply_card_click, picker_card_for
from .channel import INITIAL_PLACEHOLDER_TEXT, SURFACE_GOOGLE_CHAT
from .client import (
    acknowledge,
    close_google_chat_client,
    create_card_message,
    create_message,
    pull_messages,
    update_card_message,
)
from .commands import CommandContext, dispatch_command
from .conversation import get_or_create_google_chat_conversation
from .delivery import DEFAULT_VERBOSE_LEVEL
from .dev_admin import resolve_or_autolink_google_chat_user
from .messages import (
    MESSAGE_EVENT_TYPE,
    attachments_of,
    clicked_message_name,
    decode_pubsub_message,
    event_type,
    invoked_function,
    invoked_parameters,
    message_text,
    parse_command,
    sender_display,
    sender_email,
    sender_name,
    space_name,
    thread_name,
)
from .settings import google_chat_settings

logger = logging.getLogger(__name__)

# Pull batch size and the idle/backoff nap. The nap keeps the loop from
# spinning when the subscription returns empty or errors, without adding
# meaningful latency for a single dogfood user.
_PULL_MAX_MESSAGES = 10
_IDLE_POLL_SECONDS = 2.0


@dataclass
class GoogleChatService:
    """Holds the pull task + stop signal so the lifespan can stop it cleanly.

    Structural twin of ``TelegramService`` — owns the one background task
    that feeds the channel.
    """

    pull_task: asyncio.Task[None] | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)


def build_google_chat_service() -> GoogleChatService:
    """Construct an idle :class:`GoogleChatService` (task not yet started)."""
    return GoogleChatService()


@asynccontextmanager
async def google_chat_lifespan() -> AsyncIterator[GoogleChatService | None]:
    """Boot + tear down the Pub/Sub pull loop for the app lifespan.

    Yields ``None`` (channel disabled) when the app is in demo mode or the
    service account / Pub/Sub settings aren't configured — mirroring the
    Telegram lifespan's no-token short-circuit.
    """
    if settings.demo_mode:
        logger.info("GOOGLE_CHAT_DISABLED reason=demo_mode")
        yield None
        return
    if not has_google_chat_auth():
        logger.info("GOOGLE_CHAT_DISABLED reason=not_configured")
        yield None
        return

    service = build_google_chat_service()
    service.pull_task = asyncio.create_task(
        _pull_loop(service.stop_event),
        name="google-chat-pull",
    )
    logger.info(
        "GOOGLE_CHAT_BOOT subscription=%s", google_chat_settings.google_chat_subscription_id
    )
    try:
        yield service
    finally:
        service.stop_event.set()
        if service.pull_task is not None:
            service.pull_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await service.pull_task
        await close_google_chat_client()


async def _pull_loop(stop_event: asyncio.Event) -> None:
    """Pull → process → ack until the lifespan signals stop."""
    while not stop_event.is_set():
        try:
            handled = await _pull_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("GOOGLE_CHAT_PULL_LOOP_ERR")
            handled = False
        if not handled:
            await asyncio.sleep(_IDLE_POLL_SECONDS)


async def _pull_once() -> bool:
    """Run one pull → ack → process cycle. Returns whether work was done.

    Messages are acknowledged *before* their turns run. A real ``run_turn``
    routinely exceeds Pub/Sub's ~10s ack deadline and the channel does no
    lease extension, so acking *after* processing lets Pub/Sub redeliver the
    message mid-turn — producing a duplicate turn, duplicate persisted
    messages, double cost, and two replies. Acking first is at-most-once,
    which matches the loop's existing "ack even on failure" intent
    (``_maybe_handle`` swallows and logs its own errors).
    """
    received = await pull_messages(
        project_id=google_chat_settings.google_chat_project_id,
        subscription_id=google_chat_settings.google_chat_subscription_id,
        max_messages=_PULL_MAX_MESSAGES,
    )
    if not received:
        return False
    ack_ids: list[str] = []
    events: list[dict[str, Any] | None] = []
    for item in received:
        ack_id, event = decode_pubsub_message(item)
        if ack_id:
            ack_ids.append(ack_id)
        events.append(event)
    await acknowledge(
        project_id=google_chat_settings.google_chat_project_id,
        subscription_id=google_chat_settings.google_chat_subscription_id,
        ack_ids=ack_ids,
    )
    for event in events:
        await _maybe_handle(event)
    return True


async def _maybe_handle(event: dict[str, Any] | None) -> None:
    """Route a card click, slash command, or MESSAGE turn; ignore the rest.

    One bad event never breaks the pull loop — it is still acknowledged by
    the caller and the error is logged here.
    """
    if event is None:
        return
    try:
        if invoked_function(event):
            await _handle_card_click(event)
            return
        command = parse_command(event)
        if command is not None:
            await _handle_command_event(event, command)
        elif event_type(event) == MESSAGE_EVENT_TYPE:
            await _handle_message_event(event)
    except Exception:
        logger.exception("GOOGLE_CHAT_HANDLE_ERR space=%s", space_name(event))


@dataclass
class _ResolvedSender:
    """The bound Pawrrtal user + their Google Chat conversation."""

    user_id: uuid.UUID
    conversation: Conversation


async def _resolve_sender(event: dict[str, Any], session: AsyncSession) -> _ResolvedSender | None:
    """Resolve the inbound sender to a bound user + conversation, or ``None``.

    Single-sources the dev-admin auto-link + unbound-sender policy shared by
    the command, card-click, and message-turn paths: an unbound sender is
    logged once here and the caller skips. ``space_name`` / ``sender_*`` read
    the message, command, and card-click event shapes alike.
    """
    user_id = await resolve_or_autolink_google_chat_user(
        session=session,
        external_user_id=sender_name(event),
        space_name=space_name(event),
        display=sender_display(event),
    )
    if user_id is None:
        logger.info("GOOGLE_CHAT_UNBOUND_SENDER sender=%s", sender_name(event))
        return None
    conversation = await get_or_create_google_chat_conversation(user_id=user_id, session=session)
    return _ResolvedSender(user_id=user_id, conversation=conversation)


async def _handle_command_event(event: dict[str, Any], parsed: tuple[str, str]) -> None:
    """Resolve identity, then post a picker card (no-arg picker) or a text reply."""
    command, args = parsed
    space = space_name(event)
    if not space:
        return
    card: list[dict[str, Any]] | None = None
    reply: str | None = None
    async with async_session_maker() as session:
        resolved = await _resolve_sender(event, session)
        if resolved is None:
            return
        card = picker_card_for(command, resolved.conversation) if not args else None
        if card is None:
            reply = await dispatch_command(
                command=command,
                ctx=CommandContext(
                    user_id=resolved.user_id,
                    conversation=resolved.conversation,
                    args=args,
                    sender_resource=sender_name(event),
                    sender_email=sender_email(event),
                    session=session,
                ),
            )
    thread = thread_name(event)
    if card is not None:
        await create_card_message(space_name=space, cards=card, thread_name=thread)
    elif reply is not None:
        await create_message(space_name=space, text=reply, thread_name=thread)


async def _handle_card_click(event: dict[str, Any]) -> None:
    """Apply a picker button click and patch the card message in place."""
    message_name = clicked_message_name(event)
    if not message_name:
        return
    cards: list[dict[str, Any]] | None = None
    async with async_session_maker() as session:
        resolved = await _resolve_sender(event, session)
        if resolved is None:
            return
        cards = await apply_card_click(
            function=invoked_function(event),
            params=invoked_parameters(event),
            user_id=resolved.user_id,
            conversation=resolved.conversation,
            session=session,
        )
    if cards is not None:
        await update_card_message(message_name=message_name, cards=cards)


@dataclass
class _TurnTarget:
    """The resolved Pawrrtal context for one inbound Chat message."""

    user_id: uuid.UUID
    conversation_id: uuid.UUID
    workspace_root: Path
    workspace_id: uuid.UUID
    model_id: str
    verbose_level: int


async def _resolve_turn_target(event: dict[str, Any]) -> _TurnTarget | None:
    """Resolve the user, workspace, and conversation for an inbound message.

    Returns ``None`` when the sender isn't bound (and isn't the configured
    dev-admin) or has no workspace yet — both are logged and skipped.
    """
    async with async_session_maker() as session:
        resolved = await _resolve_sender(event, session)
        if resolved is None:
            return None
        workspace = await get_default_workspace(resolved.user_id, session)
        if workspace is None:
            logger.warning("GOOGLE_CHAT_NO_WORKSPACE user_id=%s", resolved.user_id)
            return None
        conversation = resolved.conversation
        # Read the plain column values while the row is still attached.
        return _TurnTarget(
            user_id=resolved.user_id,
            conversation_id=conversation.id,
            workspace_root=Path(workspace.path),
            workspace_id=workspace.id,
            model_id=conversation.model_id or default_model().id,
            verbose_level=(
                conversation.verbose_level
                if conversation.verbose_level is not None
                else DEFAULT_VERBOSE_LEVEL
            ),
        )


def _resolve_provider(model_id: str, workspace_root: Path) -> tuple[AILLM, str]:
    """Resolve a provider, falling back to the catalog default on a bad id.

    Returns ``(provider, effective_model_id)`` so the channel envelope and
    cost ledger record the model actually used. The catalog default is a
    tool-forwarding model, so this also keeps the channel off the
    tool-dropping CLI hosts by default.
    """
    try:
        return resolve_llm(model_id, workspace_root=workspace_root), model_id
    except (InvalidModelId, UnknownModelId) as exc:
        fallback = default_model().id
        logger.warning(
            "GOOGLE_CHAT_MODEL_FALLBACK model=%s fallback=%s reason=%s",
            model_id,
            fallback,
            exc,
        )
        return resolve_llm(fallback, workspace_root=workspace_root), fallback


async def _handle_message_event(event: dict[str, Any]) -> None:
    """Drive one full Chat turn: resolve → placeholder → attachments → run_turn."""
    text = message_text(event)
    space = space_name(event)
    has_attachments = bool(attachments_of(event))
    if not space or (not text.strip() and not has_attachments):
        return

    target = await _resolve_turn_target(event)
    if target is None:
        return

    provider, effective_model_id = _resolve_provider(target.model_id, target.workspace_root)
    agent_tools = build_agent_tools(
        workspace_root=target.workspace_root,
        user_id=target.user_id,
        workspace_id=target.workspace_id,
        surface=SURFACE_GOOGLE_CHAT,
        conversation_id=target.conversation_id,
        model_id=effective_model_id,
    )

    thread = thread_name(event)
    message_name = await create_message(
        space_name=space,
        text=INITIAL_PLACEHOLDER_TEXT,
        thread_name=thread,
    )
    if message_name is None:
        logger.warning("GOOGLE_CHAT_PLACEHOLDER_FAILED space=%s", space)
        return

    # Local import breaks the registry ↔ google_chat package import cycle.
    from app.channels.registry import resolve_channel  # noqa: PLC0415

    attachments = await collect_attachments(event)
    question = _build_question(text, attachments.annotations)

    channel_message: ChannelMessage = {
        "user_id": target.user_id,
        "conversation_id": target.conversation_id,
        "text": text or "(attachment)",
        "surface": SURFACE_GOOGLE_CHAT,
        "model_id": effective_model_id,
        "metadata": {
            "space_name": space,
            "thread_name": thread,
            "message_name": message_name,
            "verbose_level": target.verbose_level,
        },
    }
    turn_input = ChatTurnInput(
        conversation_id=target.conversation_id,
        user_id=target.user_id,
        question=question,
        provider=provider,
        channel=resolve_channel(SURFACE_GOOGLE_CHAT),
        channel_message=channel_message,
        workspace_root=target.workspace_root,
        tools=agent_tools,
        images=attachments.images or None,
        log_tag="GOOGLE_CHAT",
    )
    async for _ in run_turn(turn_input):
        pass


def _build_question(text: str, annotations: list[str]) -> str:
    """Combine the user's text with attachment annotations for the agent.

    When the message is attachment-only (no text), a short default prompt
    stands in so the agent has something to act on alongside the image or
    document context.
    """
    base = text.strip() or "Please respond to the attached file(s)."
    if not annotations:
        return base
    return base + "\n\n" + "\n".join(annotations)
