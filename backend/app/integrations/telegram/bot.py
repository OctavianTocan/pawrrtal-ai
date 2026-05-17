"""aiogram-backed Telegram bot service.

REBUILD STUB — bean ``pawrrtal-obsd`` (Phase 11) has the full spec.
Phase 10 (``pawrrtal-0v4v``) also lives here: the auto-title helpers
sit at module scope, not inside the dispatcher closure.

Thin glue between aiogram and the framework-free handlers. Two boot
modes (polling for laptops, webhook for prod) share the same handlers.
"""

# Bot token can be obtained via https://t.me/BotFather
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.core.config import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# We need to import the token from the config file
if not settings.telegram_bot_token:
    logger.info("TELEGRAM_BOT_TOKEN is not set, Telegram bot will not be started.")

# We need to set the token to the dispatcher.
TOKEN = settings.telegram_bot_token

# All handlers should be attached to the Router (or Dispatcher)
router = Router()

dispatcher = Dispatcher()
dispatcher.include_router(router)


# The 'F' here is aiogram's filter syntax that allows us to match on the message text.
@router.message(F.text)
async def handle_text(message: Message) -> None:
    """Handle the text message."""
    await message.answer("Hello, world! You said: " + (message.text or "nothing"))


@router.message(CommandStart(deep_link=True))
async def on_start(message: Message) -> None:
    sender = _sender_from_message(message)
    # TODO: This is where I left off.
    payload: str | None = _extract_start_payload(message)
    async with async_session_maker() as session:
        reply: str = await handle_start_command(sender=sender, payload=payload, session=session)
    await message.answer(reply)


async def start_telegram_bot_polling() -> None:
    """Main function to run the Telegram bot."""
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dispatcher.start_polling(bot, handle_signals=False)
