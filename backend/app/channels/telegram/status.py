"""``/status`` command for the Telegram channel.

Extracted from :mod:`app.channels.telegram.handlers` to keep that
file under the 500-line budget enforced by
``scripts/check-file-lines.mjs``. The /status surface is wholly
self-contained (pure formatters + one async handler + its own copy
constants) so it lifts cleanly into its own module.

``_VERBOSE_LABELS`` lives here rather than in ``handlers`` so the cycle
``handlers → status → handlers`` doesn't appear: ``handlers`` imports
it back from this module for ``handle_verbose_command``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import (
    get_or_create_telegram_conversation_full,
    get_user_id_for_external,
)

# Re-export so callers in ``bot.py`` import all LCM-flavoured handlers
# from one module path — keeping ``bot.py``'s fan-out under sentrux's
# ``no_god_files`` budget (issue #303 added the second helper). The
# underlying implementations live in their own per-command files to
# keep each module focused on one command.
from app.channels.telegram.compact_command import (
    handle_compact_command as handle_compact_command,  # noqa: PLC0414
)
from app.channels.telegram.lcm_status import (
    handle_lcm_command as handle_lcm_command,  # noqa: PLC0414
)
from app.channels.telegram.model_defaults import resolve_effective_model_id
from app.conversations.crud import ConversationStatus, get_conversation_status
from app.infrastructure.config import settings
from app.providers.catalog import find, first_catalog_model
from app.providers.model_id import InvalidModelId, parse_model_id


class _TelegramSenderLike(Protocol):
    """Structural type for the subset of ``TelegramSender`` /status needs.

    Declared as a Protocol so this module does not import from
    ``app.channels.telegram.handlers`` — sentrux's ``max_cycles=0``
    architecture rule forbids any handlers↔status import edge (even
    under ``TYPE_CHECKING``).  The concrete ``TelegramSender``
    dataclass in ``handlers.py`` already satisfies this shape, so
    callers pass it unchanged.
    """

    @property
    def user_id(self) -> int:
        """Telegram numeric user id."""
        ...

    @property
    def chat_id(self) -> int:
        """Telegram chat id (DM or group)."""
        ...

    @property
    def thread_id(self) -> int | None:
        """Telegram topic thread id, or ``None`` outside a topic."""
        ...


logger = logging.getLogger(__name__)

# Telegram channel id used to look up bindings.  Mirrors the constant in
# ``handlers`` (kept in sync because the binding lookup is duplicated
# here to avoid a runtime import cycle).
_PROVIDER = "telegram"

# Human-readable labels used in /verbose and /status replies.
_VERBOSE_LABELS: dict[int, str] = {
    0: "quiet",
    1: "normal",
    2: "detailed",
}

_STATUS_NOT_BOUND_MESSAGE = "Connect your account first before asking for status."
_STATUS_NO_CONVERSATION_MESSAGE = (
    "📊 Pawrrtal gateway\n\n"
    "⏱  Bot up: {uptime} (this worker)\n\n"
    "💬 No conversation yet — send a message to start one."
)
_STATUS_MESSAGE = (
    "📊 Pawrrtal gateway\n\n"
    "⏱  Bot up: {uptime} (this worker)\n"
    "🤖 Model: {model_display} (<code>{model_id}</code>){model_warning}\n"
    "🔊 Verbose: {verbose_level} ({verbose_label})\n"
    "🧠 Thinking: {reasoning_label}\n\n"
    "💬 This conversation\n"
    "   • Started: {started_ago} ago\n"
    "   • Messages: {messages} ({user_messages} yours, {assistant_messages} assistant)\n"
    "   • Tokens: {tokens}\n"
    "   • Cost: {cost}\n"
    "   • Status: {run_status}"
)
_STATUS_THREAD_LINE = "\n🧵 Topic thread: <code>{thread_id}</code>"
_STATUS_MODEL_WARNING_SUFFIX = " ⚠️ catalog lookup failed"
_STATUS_RUN_RUNNING = "running"
_STATUS_RUN_IDLE = "idle"
_REASONING_LABEL_DEFAULT = "default (provider-picked)"
_REASONING_LABEL_UNSUPPORTED = "n/a (model doesn't support)"
_COST_DECIMAL_PLACES = 4
_COST_UNAVAILABLE = "n/a (provider did not report cost)"

_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3_600
_SECONDS_PER_DAY = 86_400


def _format_duration(seconds: float) -> str:
    """Render a positive duration as ``"3d 1h"`` / ``"4h 12m"`` / ``"34s"``.

    Falls back to ``"0s"`` for non-positive inputs so the formatter never
    yields an empty string.
    """
    total = int(max(0.0, seconds))
    days, rem = divmod(total, _SECONDS_PER_DAY)
    hours, rem = divmod(rem, _SECONDS_PER_HOUR)
    minutes, secs = divmod(rem, _SECONDS_PER_MINUTE)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _format_token_count(n: int) -> str:
    """Render a non-negative token count with thousands separators."""
    return f"{max(0, int(n)):,}"


def _format_model_display(model_id: str | None) -> tuple[str, str, str]:
    """Resolve a stored model_id to ``(display_name, canonical_id, warning)``.

    Falls back to the catalog default when ``model_id`` is ``None``.
    When the ID is set but absent from the catalog, returns the raw ID
    with a warning suffix so the status reply still renders without
    crashing.
    """
    canonical = model_id or first_catalog_model().id
    try:
        parsed = parse_model_id(canonical)
        entry = find(parsed)
    except InvalidModelId:
        entry = None

    if entry is None:
        return canonical, canonical, _STATUS_MODEL_WARNING_SUFFIX
    return entry.short_name, entry.id, ""


def _resolve_verbose(level: int | None) -> tuple[int, str]:
    """Return ``(effective_level, label)`` for the status reply."""
    effective = level if level is not None else int(settings.telegram_verbose_default)
    return effective, _VERBOSE_LABELS.get(effective, "unknown")


def _resolve_reasoning_label(
    reasoning_effort: str | None,
    *,
    model_id: str | None,
) -> str:
    """Render the ``🧠 Thinking`` line for the status reply.

    Returns the persisted effort verbatim when one is set, otherwise:

    * ``"n/a (model doesn't support)"`` when the catalog entry exposes
      no reasoning levels — surfaces honestly that a /thinking choice
      would do nothing on this model.
    * ``"default (provider-picked)"`` when the model does support
      reasoning levels but no per-conversation override is stored.
    """
    if reasoning_effort:
        return reasoning_effort
    canonical = model_id or first_catalog_model().id
    try:
        parsed = parse_model_id(canonical)
        entry = find(parsed)
    except InvalidModelId:
        entry = None
    if entry is None or not entry.supports_reasoning:
        return _REASONING_LABEL_UNSUPPORTED
    return _REASONING_LABEL_DEFAULT


def _format_cost_usd(cost_usd: float, *, has_messages: bool, has_usage: bool) -> str:
    """Render the ``💵 Cost`` line.

    Mirrors the tokens-line honesty pattern: when a conversation has
    messages but the provider didn't report usage tokens at all
    (``has_usage=False``), surface that explicitly rather than print
    a misleading ``$0.0000``. A genuine ``$0.00`` turn (the user
    /stop'd before the first token, or the model produced no output)
    still renders as ``$0.0000`` because tokens were reported even
    though the cost was zero.
    """
    if has_messages and not has_usage:
        return _COST_UNAVAILABLE
    return f"${cost_usd:.{_COST_DECIMAL_PLACES}f}"


def _now_utc() -> datetime:
    """Indirection seam for tests that want to freeze 'now'."""
    return datetime.now(UTC)


def _render_status_message(
    *,
    bot_uptime_seconds: float,
    status: ConversationStatus,
    run_active: bool,
    thread_id: int | None,
    now: datetime,
    effective_model_id: str | None = None,
) -> str:
    """Pure formatter used by ``handle_status_command`` and its tests.

    ``effective_model_id`` is the resolved canonical ID after walking
    the conversation → user-default → catalog chain. Callers should
    pre-resolve via :func:`resolve_effective_model_id`; if omitted,
    the formatter falls back to ``status.model_id`` directly (used by
    the existing test suite that doesn't model the user-default path).
    """
    rendered_model_id = effective_model_id if effective_model_id is not None else status.model_id
    model_display, model_canonical, model_warning = _format_model_display(rendered_model_id)
    verbose_level, verbose_label = _resolve_verbose(status.verbose_level)
    # ``Conversation.created_at`` is a tz-naive DateTime column in the DB —
    # all timestamps in this app are written in UTC. Normalize so the
    # subtraction never trips on mixed naive/aware operands.
    started_at = status.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    started_ago_seconds = (now - started_at).total_seconds()

    # Tokens come from cost_ledger, which is only populated for providers
    # that emit ``usage`` stream events. Gemini currently doesn't, so its
    # turns land with zero tokens despite real activity. Render an honest
    # placeholder rather than a misleading "0 in / 0 out" in that case.
    has_messages = status.message_count > 0
    has_usage = status.total_input_tokens > 0 or status.total_output_tokens > 0
    if has_messages and not has_usage:
        tokens_line = "n/a (provider did not report usage)"
    else:
        tokens_line = (
            f"{_format_token_count(status.total_input_tokens)} in / "
            f"{_format_token_count(status.total_output_tokens)} out"
        )

    reasoning_label = _resolve_reasoning_label(status.reasoning_effort, model_id=rendered_model_id)
    cost_line = _format_cost_usd(
        status.total_cost_usd, has_messages=has_messages, has_usage=has_usage
    )

    body = _STATUS_MESSAGE.format(
        uptime=_format_duration(bot_uptime_seconds),
        model_display=model_display,
        model_id=model_canonical,
        model_warning=model_warning,
        verbose_level=verbose_level,
        verbose_label=verbose_label,
        reasoning_label=reasoning_label,
        started_ago=_format_duration(started_ago_seconds),
        messages=status.message_count,
        user_messages=status.user_message_count,
        assistant_messages=status.assistant_message_count,
        tokens=tokens_line,
        cost=cost_line,
        run_status=_STATUS_RUN_RUNNING if run_active else _STATUS_RUN_IDLE,
    )
    if thread_id is not None:
        body += _STATUS_THREAD_LINE.format(thread_id=thread_id)
    return body


async def handle_status_command(
    *,
    sender: _TelegramSenderLike,
    session: AsyncSession,
    bot_uptime_seconds: float,
    is_chat_run_active: Callable[[int], bool],
) -> str:
    """Render the gateway + per-conversation status reply for ``/status``.

    Args:
        sender: Normalized sender identity (carries ``chat_id`` for the
            run-status lookup and ``thread_id`` for topic chats).
        session: Async database session.
        bot_uptime_seconds: Seconds since this worker booted (passed in so
            the handler stays a pure function over its inputs).
        is_chat_run_active: Predicate that returns whether ``chat_id`` has
            an in-flight agent run on this worker. Process-local — a run
            on another worker reads as idle here.

    Returns:
        Reply string the bot should send immediately.
    """
    pawrrtal_user_id = await get_user_id_for_external(
        provider=_PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if pawrrtal_user_id is None:
        return _STATUS_NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )
    status = await get_conversation_status(conversation_id=conversation.id, session=session)
    if status is None:
        # The row was deleted between resolution and status read — extremely
        # unlikely but render the gateway-only view rather than crashing.
        return _STATUS_NO_CONVERSATION_MESSAGE.format(uptime=_format_duration(bot_uptime_seconds))

    effective_model_id = resolve_effective_model_id(conversation_model_id=status.model_id)
    return _render_status_message(
        bot_uptime_seconds=bot_uptime_seconds,
        status=status,
        run_active=is_chat_run_active(sender.chat_id),
        thread_id=sender.thread_id,
        now=_now_utc(),
        effective_model_id=effective_model_id,
    )
