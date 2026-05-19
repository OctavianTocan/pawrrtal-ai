"""Shared dataclass for a Telegram message sender.

Lives in its own module so the Telegram package — handlers, dev-admin
auto-link, model picker, status formatters — can all share one source
of truth without forming an import cycle through ``handlers``. The
package's previous workaround was a per-consumer ``TelegramSenderLike``
``Protocol`` (in ``dev_admin``, ``model_picker``, ``status``,
``lcm_status``); those can fold back to the real type as a follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramSender:
    """Stable subset of an aiogram ``Message.from_user`` we need.

    Modeled as a plain dataclass so handler tests don't have to import aiogram
    or build a fake bot.
    """

    user_id: int
    chat_id: int
    username: str | None
    full_name: str | None
    # Telegram Bot API 9.3+ topic thread ID.  None when topics not enabled.
    thread_id: int | None = None
