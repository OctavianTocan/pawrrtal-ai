"""Drives one full LLM turn for a Telegram message.

Extracted from ``bot.py`` to keep the dispatcher closures narrow enough
to satisfy the project's complexity cap. Sends a placeholder reply,
resolves the provider (with the auto-clear safety net), builds the
channel message, streams the response, and finally fires the
auto-title pass.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

# ``ChannelMessage`` is re-exported via :mod:`app.channels` (its
# ``__init__.py`` already does the lift) so this module imports both
# ``resolve_channel`` and ``ChannelMessage`` from the same module —
# one fewer fan-out hit for sentrux's ``no_god_files`` budget.
from app.channels import ChannelMessage, resolve_channel

# ``render_initial`` is re-exported via :mod:`app.channels.telegram`
# to keep this module's fan-out small.
from app.channels.telegram import SURFACE_TELEGRAM, make_telegram_sender, render_initial
from app.channels.turn_runner import ChatTurnInput, run_turn
from app.core.agent_tools import build_agent_tools
from app.core.config import settings
from app.crud.workspace import get_default_workspace
from app.db import async_session_maker
from app.integrations.telegram.bot.auto_title import maybe_set_auto_title
from app.integrations.telegram.bot.state import _running_tasks
from app.integrations.telegram.bot.typing_indicator import (
    maintain_typing_indicator,
    reply_parameters,
)
from app.integrations.telegram.bot_permissions import build_telegram_permission_check
from app.integrations.telegram.bot_provider_resolution import (
    resolve_provider_with_auto_clear,
)
from app.integrations.telegram.handlers import TelegramTurnContext

# The reasoning-effort backstop lives in its own module so this module
# doesn't take a separate fan-out hit on the resolver + DB seam +
# notice formatter.
from app.integrations.telegram.reasoning_notify import normalize_reasoning_and_notify

if TYPE_CHECKING:
    from aiogram.types import Message

logger = logging.getLogger(__name__)


def _compose_user_text(message: Message, text_annotations: list[str] | None) -> str:
    """Combine the inbound text/caption with attachment annotations.

    A text-only message uses just the text; an attachment-only message
    uses just the annotations; messages with both get them joined by a
    blank line so the agent can distinguish the user's message from the
    metadata.
    """
    base_text = (message.text or message.caption or "").strip()
    annotation_block = "\n".join(text_annotations or []).strip()
    if base_text and annotation_block:
        return f"{base_text}\n\n{annotation_block}"
    # Either: text-only message, attachment-only message, or both
    # — string concat falls through to whichever is non-empty.
    return base_text or annotation_block


# TODO: This is pretty nonsensical. We have a custom entire chat impkementation that just duplicates the logic here.
async def run_llm_turn(
    *,
    message: Message,
    context: TelegramTurnContext,
    images: list[dict[str, str]] | None = None,
    text_annotations: list[str] | None = None,
) -> None:
    """Drive the LLM streaming pipeline for one Telegram turn.

    Extracted from ``_on_message`` to keep that dispatcher closure narrow
    enough to satisfy the project's complexity cap.  Sends a placeholder
    reply, resolves the provider (with the auto-clear safety net),
    builds the channel message, streams the response, and finally fires
    the auto-title pass.

    Args:
        message: The inbound aiogram ``Message`` (used for ``answer``,
            ``chat.id``, ``bot``, and ``message_thread_id``).
        context: Resolved turn context from ``handle_plain_message``.
        images: Image inputs collected via :func:`collect_attachments`
            (#305). Forwarded to ``ChatTurnInput.images`` so the
            provider can pass them as multimodal content blocks.
        text_annotations: ``"User sent X."`` lines appended to the
            user message body so the agent has metadata for voice /
            document attachments we couldn't fully extract (#304, #305).
    """
    user_text = _compose_user_text(message, text_annotations)
    if message.bot is None:
        raise RuntimeError("Telegram message has no bot; refusing to stream.")
    thinking_msg = await message.answer(
        render_initial(),
        reply_parameters=reply_parameters(message.message_id),
    )

    async with async_session_maker() as ws_session:
        workspace = await get_default_workspace(context.pawrrtal_user_id, ws_session)

    tg_sender = make_telegram_sender(
        message.bot,
        message.chat.id,
        message_thread_id=context.thread_id,
        reply_to_message_id=message.message_id,
    )
    agent_tools = (
        build_agent_tools(
            workspace_root=Path(workspace.path),
            user_id=context.pawrrtal_user_id,
            workspace_id=workspace.id,
            send_fn=tg_sender,
            surface="telegram",
        )
        if workspace is not None
        else []
    )

    provider, warning = await resolve_provider_with_auto_clear(
        context,
        workspace_root=Path(workspace.path) if workspace is not None else None,
    )
    if warning is not None:
        await message.answer(warning, reply_parameters=reply_parameters(message.message_id))

    channel_message: ChannelMessage = {
        "user_id": context.pawrrtal_user_id,
        "conversation_id": context.conversation_id,
        "text": user_text,
        "surface": SURFACE_TELEGRAM,
        "model_id": context.model_id,
        "metadata": {
            "bot": message.bot,
            "chat_id": message.chat.id,
            "message_id": thinking_msg.message_id,
            "reply_to_message_id": message.message_id,
            "message_thread_id": context.thread_id,
        },
    }

    # Backstop: re-validate the stored reasoning_effort against the
    # current model. Telegram's /thinking picker writes the column,
    # but model changes (via /model, the picker, or any future
    # surface) can leave the stored value out of sync with what the
    # model honours. The shared resolver in
    # `app.core.providers.reasoning` adapts or clears the override;
    # the helper sends a Telegram notice whenever a change happens
    # so the new behaviour isn't silent. Returns ``None`` for the
    # "let the provider pick its default" case.
    effective_effort = await normalize_reasoning_and_notify(
        message=message,
        conversation_id=context.conversation_id,
        model_id=context.model_id,
    )

    turn_input = ChatTurnInput(
        conversation_id=context.conversation_id,
        user_id=context.pawrrtal_user_id,
        question=user_text,
        provider=provider,
        channel=resolve_channel(SURFACE_TELEGRAM),
        channel_message=channel_message,
        workspace_root=Path(workspace.path) if workspace is not None else None,
        tools=agent_tools,
        images=images,
        permission_check=build_telegram_permission_check(
            context,
            Path(workspace.path) if workspace is not None else None,
        ),
        log_tag="TELEGRAM",
        log_extras={"chat_id": message.chat.id},
        verbose_level=(
            context.verbose_level
            if context.verbose_level is not None
            else settings.telegram_verbose_default
        ),
        reasoning_effort=effective_effort,
    )

    async def _do_stream() -> None:
        async for _ in run_turn(turn_input):
            pass

    # Cancel any previous stream for this chat before starting the new one.
    chat_id = message.chat.id
    old_task = _running_tasks.pop(chat_id, None)
    if old_task is not None and not old_task.done():
        old_task.cancel()

    # PR 07: persistent typing indicator. Telegram clears the
    # "typing…" status after ~5 seconds, so we refresh on a timer
    # for the whole duration of the agent run. Cancelled in the
    # finally block alongside the stream task so a chat that
    # finished (or was /stop'd) doesn't keep the indicator up.
    typing_task = asyncio.create_task(
        maintain_typing_indicator(message.bot, chat_id, context.thread_id),
        name=f"telegram-typing-{chat_id}",
    )

    task: asyncio.Task[None] = asyncio.create_task(_do_stream())
    _running_tasks[chat_id] = task
    try:
        await task
    except asyncio.CancelledError:
        logger.info("TELEGRAM_STREAM_CANCELLED chat_id=%s", chat_id)
    finally:
        _running_tasks.pop(chat_id, None)
        typing_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await typing_task

    # Auto-title: derive a title from the first user message and
    # rename the Telegram topic thread to match.  Fires once only
    # (gated by title_set_by IS NULL).  Errors are swallowed so a
    # topic-rename failure never breaks the conversation.
    try:
        await maybe_set_auto_title(
            bot=message.bot,
            conversation_id=context.conversation_id,
            user_text=user_text,
            chat_id=message.chat.id,
            thread_id=context.thread_id,
        )
    except Exception:
        logger.warning("TELEGRAM_AUTO_TITLE_FAILED", exc_info=True)
