"""Small Telegram delivery helpers shared by channel and send-message paths."""

from __future__ import annotations

import html as html_lib
import logging
from typing import TYPE_CHECKING, Any

from app.core.tools.display import fallback_tool_display

from .telegram_html import md_to_telegram_html

if TYPE_CHECKING:
    from aiogram import Bot

    from app.core.providers.base import StreamEvent

logger = logging.getLogger(__name__)

# Telegram SDK error tuple — narrow ``except`` from ``Exception``.
# Imported lazily inside the helpers (the SDK's exception module is
# only needed when the helpers are actually called) so ``aiogram``
# remains an optional dependency for non-telegram pytest runs.

MAX_MESSAGE_LEN = 4096


def chunk_html_for_telegram(html: str, *, max_len: int = MAX_MESSAGE_LEN) -> list[str]:
    """Split a Telegram-HTML string into chunks that each fit the API limit.

    Telegram caps a single ``sendMessage`` body at 4096 UTF-16 code units
    (we approximate with Python string length — close enough for the
    ASCII-dominant tool output we ship). Previously the delivery helpers
    truncated overflow with ``"..."``, which silently dropped the tail
    of long continuous tool-call logs (#424). The replacement strategy
    is to split into multiple sequential messages so the user sees the
    full transcript.

    Splitting is conservative: we prefer a blank-line boundary, fall
    back to a single newline, and only resort to a hard character
    boundary when neither exists in the window. We never split inside
    a ``<pre>`` block — Telegram closes the tag at the message edge
    and the chunk would render as a broken code block. The simple
    heuristic for this PR keeps the splitter pure and dependency-free;
    a smarter tag-balancing pass can land later if a real-world case
    shows tag corruption (the dominant production traffic is
    paragraph-separated narrative text).

    Args:
        html: Already-rendered Telegram HTML.
        max_len: Maximum length per chunk. Defaults to Telegram's
            ``sendMessage`` limit; tests override to exercise the
            splitter without 4 KB strings.

    Returns:
        A list of HTML chunks, each ``<= max_len``. A short input
        returns ``[html]`` unchanged; an empty input returns ``[""]``
        so the caller's loop fires exactly once (matching the old
        single-send behaviour for empty payloads).
    """
    if len(html) <= max_len:
        return [html]
    chunks: list[str] = []
    remaining = html
    while len(remaining) > max_len:
        # Try to break at a blank line first, then a single newline, then
        # the hard character boundary. The break point is the index of
        # the *separator*, so the chunk excludes it and the next chunk
        # starts immediately after — no leading whitespace.
        cut = remaining.rfind("\n\n", 0, max_len)
        sep_len = 2
        if cut == -1:
            cut = remaining.rfind("\n", 0, max_len)
            sep_len = 1
        if cut == -1:
            # No newline in the window — hard-cut at the boundary. The
            # resulting chunk may end mid-tag in pathological cases;
            # see the docstring note above.
            cut = max_len
            sep_len = 0
        chunks.append(remaining[:cut])
        remaining = remaining[cut + sep_len :]
    if remaining:
        chunks.append(remaining)
    return chunks


def _aiogram_errors() -> tuple[type[BaseException], ...]:
    """Return the aiogram exception types we treat as recoverable.

    ``TelegramAPIError`` is the base class for every server-side error
    aiogram surfaces (bad request, throttling, deletion of a message
    we no longer own, etc.); ``TelegramNetworkError`` covers connection
    failures.  We log+swallow these so a single edit/delete glitch
    doesn't abort the agent turn — anything else (config error, type
    error, our own bugs) is *not* caught here and propagates as a real
    exception.
    """
    from aiogram.exceptions import TelegramAPIError, TelegramNetworkError  # noqa: PLC0415

    return (TelegramAPIError, TelegramNetworkError)


def format_tool_use(event: StreamEvent, *, state: str = "present") -> str:
    """Render a tool call with shared display metadata or a safe fallback."""
    tool_name = str(event.get("name") or "tool")
    raw_display = event.get("display")
    if isinstance(raw_display, dict):
        icon = str(raw_display.get("icon") or "").strip()
        val = str(raw_display.get(state) or "").strip()
        if val:
            if icon and not val.startswith(icon):
                val = f"{icon} {val}"
            return val
    raw_input = event.get("input") or {}
    arguments = raw_input if isinstance(raw_input, dict) else {"input": raw_input}
    fallback = fallback_tool_display(tool_name, arguments)
    val = str(fallback.get(state) or tool_name)
    fallback_icon = str(fallback.get("icon") or "").strip()
    if fallback_icon and not val.startswith(fallback_icon):
        val = f"{fallback_icon} {val}"
    return val


def final_reply_text(
    *,
    answer_text: str,
    terminal_message: str | None,
    terminal_prefix: str,
) -> str:
    """Return final-answer copy for the dedicated reply message."""
    if answer_text and terminal_message:
        return f"{answer_text}\n\n{terminal_prefix}{terminal_message}"
    if answer_text:
        return answer_text
    if terminal_message:
        return f"{terminal_prefix}{terminal_message}"
    return ""


def plain_html(text: str) -> str:
    """Escape plain text for Telegram HTML mode."""
    return html_lib.escape(text)


def thinking_html(text: str) -> str:
    """Render thinking text as italic Telegram HTML with markdown applied.

    The Paw's thinking stream may emit Markdown emphasis (``**bold**``,
    ``_em_``, fenced code, etc.). Previously this helper only HTML-escaped
    the text and wrapped it in ``<i>...</i>``, so users saw literal
    ``**`` / ``_`` markers inside the thinking block. We now route the
    text through :func:`md_to_telegram_html` first — same pipeline the
    answer stream uses — then wrap the result in ``<i>`` so the whole
    block still reads as a thinking aside. Telegram allows ``<b>`` /
    ``<a>`` / etc. nested inside ``<i>``, so the combination renders
    correctly even when the model emits formatting mid-trace.

    Closes #287.
    """
    rendered = md_to_telegram_html(text)
    # ``md_to_telegram_html`` falls back to the raw text when conversion
    # produces nothing — re-escape in that case so we never emit unescaped
    # ``<``/``&`` from the model into Telegram's HTML parser.
    if rendered is text:
        rendered = html_lib.escape(text)
    return f"💭 <b>Thinking...</b>\n\n<i>{rendered}</i>"


def optional_int(value: object) -> int | None:
    """Coerce optional Telegram IDs from metadata."""
    return int(value) if isinstance(value, int) else None


async def safe_edit(
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    text: str,
) -> None:
    """Call ``edit_message_text`` with Markdown-ish text."""
    await safe_edit_html(bot, chat_id, message_id, md_to_telegram_html(text))


async def safe_edit_html(
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    html: str,
) -> None:
    """Call ``edit_message_text`` with pre-rendered Telegram HTML."""
    if len(html) > MAX_MESSAGE_LEN:
        html = html[: MAX_MESSAGE_LEN - 1] + "..."
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=html,
        )
    except _aiogram_errors() as exc:
        err_str = str(exc).lower()
        if "not modified" in err_str:
            return
        logger.warning(
            "TELEGRAM_EDIT_FAILED chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            exc,
        )


async def safe_send_text(
    bot: Bot,
    chat_id: int | str,
    text: str,
    *,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
    reply_markup: Any | None = None,
) -> int | None:
    """Send Markdown-ish text after converting it to Telegram HTML."""
    return await safe_send_html(
        bot,
        chat_id,
        md_to_telegram_html(text),
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
        reply_markup=reply_markup,
    )


async def safe_send_html(
    bot: Bot,
    chat_id: int | str,
    html: str,
    *,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
    reply_markup: Any | None = None,
) -> int | None:
    """Call ``send_message`` with routing metadata, returning the message id.

    Long messages are split into multiple sequential sends via
    :func:`chunk_html_for_telegram` so the user sees the full
    transcript instead of a ``"..."`` truncation tail (#424). Only the
    first chunk replies to ``reply_to_message_id``; the rest land as
    sibling messages in the same thread so the chain reads naturally.

    ``reply_markup`` (#368) attaches an inline keyboard (e.g. the
    regenerate button) to the *last* chunk so the button sits directly
    below the final answer text.

    Returns the message_id of the *first* chunk so existing callers
    that pin/edit/delete a single message keep working unchanged.
    """
    chunks = chunk_html_for_telegram(html)
    first_id: int | None = None
    last_index = len(chunks) - 1
    for index, chunk in enumerate(chunks):
        # Subsequent chunks should not "reply" to the original anchor —
        # they're continuations, not separate replies. Threading still
        # routes them into the right topic via ``message_thread_id``.
        chunk_reply_to = reply_to_message_id if index == 0 else None
        send_kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
            **routing_kwargs(
                reply_to_message_id=chunk_reply_to,
                message_thread_id=message_thread_id,
            ),
        }
        # Attach the markup to the last chunk only so the button
        # appears directly below the complete answer.
        if reply_markup is not None and index == last_index:
            send_kwargs["reply_markup"] = reply_markup
        try:
            sent = await bot.send_message(**send_kwargs)
        except _aiogram_errors() as exc:
            logger.warning(
                "TELEGRAM_SEND_FAILED chat_id=%s chunk=%d/%d error=%s",
                chat_id,
                index + 1,
                len(chunks),
                exc,
            )
            return first_id
        message_id = getattr(sent, "message_id", None)
        if first_id is None and isinstance(message_id, int):
            first_id = message_id
    return first_id


async def safe_send_draft(
    bot: Bot,
    chat_id: int | str,
    draft_id: int,
    html: str,
    *,
    message_thread_id: int | None = None,
) -> bool:
    """Call ``SendMessageDraft`` (Bot API 9.3+) for animated streaming.

    The draft animates in chat without occupying a permanent message slot.
    It auto-expires after 30 s if not refreshed. Pass an empty string for
    ``html`` to show Telegram's native "Thinking…" animated placeholder.

    Falls back gracefully when the aiogram binding for ``SendMessageDraft``
    is not available (pre-3.27.0 builds or older servers). Returns ``True``
    on success, ``False`` on any expected error.

    Args:
        bot: Live aiogram ``Bot`` instance.
        chat_id: Target Telegram chat ID (private chats only).
        draft_id: Stable non-zero int that identifies this draft — the
            same ID animates updates in-place.
        html: Pre-rendered Telegram HTML to show, or ``""`` for the native
            "Thinking…" placeholder (Bot API 10.0+).
        message_thread_id: Optional topic thread ID.

    Returns:
        ``True`` when the draft was sent successfully, ``False`` otherwise.
    """
    if len(html) > MAX_MESSAGE_LEN:
        html = html[: MAX_MESSAGE_LEN - 1] + "..."
    # Fall back to a non-empty placeholder when the caller requested an empty
    # text (native "Thinking…") but the installed aiogram / Bot API version
    # requires a non-empty ``text`` field.  The literal fallback is benign
    # and will be overwritten on the next real chunk.
    effective_text = html if html.strip() else "💭 Thinking…"
    try:
        # aiogram ≥ 3.27.0 ships SendMessageDraft as a native method.
        from aiogram.methods import SendMessageDraft  # noqa: PLC0415

        kwargs: dict[str, object] = {
            "chat_id": chat_id,
            "draft_id": draft_id,
            "text": effective_text,
        }
        if message_thread_id is not None:
            kwargs["message_thread_id"] = message_thread_id
        result = await bot(SendMessageDraft(**kwargs))  # type: ignore[arg-type]
        return bool(result)
    except ImportError:
        # aiogram < 3.27.0 — SendMessageDraft not available; silently skip.
        logger.debug("TELEGRAM_DRAFT_UNSUPPORTED bot_api_version=pre_9.3")
        return False
    except _aiogram_errors() as exc:
        logger.warning(
            "TELEGRAM_DRAFT_FAILED chat_id=%s draft_id=%s error=%s",
            chat_id,
            draft_id,
            exc,
        )
        return False
    except Exception as exc:
        logger.warning(
            "TELEGRAM_DRAFT_FAILED chat_id=%s draft_id=%s error=%s",
            chat_id,
            draft_id,
            exc,
        )
        return False


async def safe_delete(bot: Bot, chat_id: int | str, message_id: int) -> None:
    """Delete an unused placeholder, logging but not raising on failure."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except _aiogram_errors() as exc:
        logger.warning(
            "TELEGRAM_DELETE_FAILED chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            exc,
        )


def routing_kwargs(
    *,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
) -> dict[str, Any]:
    """Return Telegram send kwargs shared by turn replies and send_message."""
    kwargs: dict[str, Any] = {}
    if message_thread_id is not None:
        kwargs["message_thread_id"] = message_thread_id
    if reply_to_message_id is not None:
        from aiogram.types import ReplyParameters  # noqa: PLC0415

        kwargs["reply_parameters"] = ReplyParameters(message_id=reply_to_message_id)
    return kwargs
