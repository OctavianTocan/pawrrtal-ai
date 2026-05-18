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
from aiogram.types.user import User

from app.core.config import settings
from app.db import async_session_maker
from app.integrations.telegram.handlers import TelegramSender, handle_start_command

# ``"/start <code>"`` splits into exactly two parts; below this means no payload.
_START_COMMAND_PARTS_WITH_PAYLOAD = 2

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


def _sender_from_message(message: Message) -> TelegramSender:
    """Project an aiogram ``Message`` onto our framework-free dataclass."""
    user: User | None = message.from_user
    # This ignores anonymous channel posts, which we don't care about here.
    if user is None:
        raise RuntimeError("Telegram message has no frm_user; refusing to dispatch.")

    return TelegramSender(
        user_id=user.id,
        chat_id=message.chat.id,
        username=user.username,
        # Bot API 9.3+: present when the message lives in a topic thread.
        # None for ordinary DMs without topics enabled.
        thread_id=message.message_thread_id,
    )


def _extract_start_payload(text: str) -> str | None:
    """Return the argument after ``/start`` (Telegram deep-link payload), if any."""
    parts: list[str] = text.strip().split(maxsplit=1)

    if len(parts) < _START_COMMAND_PARTS_WITH_PAYLOAD:
        return None

    return parts[1].strip() or None


@router.message(CommandStart(deep_link=True))
async def on_start(message: Message) -> None:
    """Handle the /start command."""
    # Get information about the sender from the message.
    sender: TelegramSender = _sender_from_message(message)
    # Extract the command and the payload (if any).
    payload: str | None = _extract_start_payload(message.text or "")
    # Handle the start command.
    async with async_session_maker() as session:
        # Call to the handler for this function itself, so it can take care of it.
        reply: str = await handle_start_command(sender=sender, payload=payload, session=session)
    # Reply.
    await message.answer(reply)


async def start_telegram_bot_polling() -> None:
    """Main function to run the Telegram bot."""
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dispatcher.start_polling(bot, handle_signals=False)


# TODO: I want to implement this properly, but I need to figure out how to do it.
# @dataclass
# class TelegramService:
#     """Holds the aiogram primitives so the lifespan can stop them cleanly."""

#     # Instance of the bot.
#     bot: Bot
