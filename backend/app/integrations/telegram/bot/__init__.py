"""Telegram bot package.

Splits the aiogram glue into focused modules — see each file's docstring
for what lives where. External callers should import only from this
package surface; the inner modules are internal layout that may move.

Public surface:

- ``TelegramService`` / ``build_telegram_service`` / ``telegram_lifespan``
  — the aiogram primitives and lifespan helper imported by
  ``backend/main.py`` and the package ``__init__.py``.
- ``refresh_telegram_commands`` / ``_refresh_telegram_commands_best_effort``
  — slash-command menu publishing, exercised directly by the unit tests
  in ``backend/tests/test_telegram_channel.py``.
- ``get_bot_uptime_seconds`` / ``is_chat_run_active`` — process-local
  probes used by the ``/status`` command handler.
"""

from app.integrations.telegram.bot.service import (
    TelegramService,
    _refresh_telegram_commands_best_effort,
    build_telegram_service,
    refresh_telegram_commands,
    telegram_lifespan,
)
from app.integrations.telegram.bot.state import (
    get_bot_uptime_seconds,
    is_chat_run_active,
)

__all__ = [
    "TelegramService",
    "_refresh_telegram_commands_best_effort",
    "build_telegram_service",
    "get_bot_uptime_seconds",
    "is_chat_run_active",
    "refresh_telegram_commands",
    "telegram_lifespan",
]
