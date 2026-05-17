"""Telegram channel adapter.

REBUILD STUB — see the ``Telegram channel: end-to-end backend rebuild``
epic (``pawrrtal-l65f``). Phases 8, 9, 10, 11 fill in the modules in this
package.

Bridges the Telegram Bot API to Nexus. Everything provider-specific
(aiogram dispatcher, message formatting, polling/webhook split) lives
here; the rest of the codebase stays Telegram-agnostic.
"""

# TODO(pawrrtal-obsd): After Phase 11 (`bot.py` rebuilt), restore the
#   public re-exports the FastAPI lifespan and main.py expect:
#
#     from app.integrations.telegram.bot import (
#         TelegramService,
#         build_telegram_service,
#         telegram_lifespan,
#     )
#
#     __all__ = ["TelegramService", "build_telegram_service", "telegram_lifespan"]
#
#   `backend/main.py` imports `telegram_lifespan` from this module; without
#   the re-export the FastAPI app fails at startup.
