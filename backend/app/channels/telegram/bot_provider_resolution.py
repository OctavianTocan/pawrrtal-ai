"""Provider-selection helper with auto-clear safety net.

Extracted from :mod:`app.channels.telegram.bot` to keep that module's
fan-out under the sentrux god-file threshold (15). The catalog / model-id
machinery used by this helper accounts for ~4 of bot.py's import edges;
hoisting it out concentrates them in one place.

See ``resolve_provider_with_auto_clear`` for the auto-clear contract.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.channels.telegram.handlers import TelegramTurnContext
from app.conversations.settings import update_conversation_model
from app.infrastructure.database.legacy import async_session_maker
from app.providers.selection import ProviderSelection, provider_or_default

logger = logging.getLogger(__name__)


async def resolve_provider_with_auto_clear(
    context: TelegramTurnContext,
    *,
    workspace_root: Path | None = None,
) -> tuple[ProviderSelection, str | None]:
    """Select a provider for ``context.model_id`` with an auto-clear safety net.

    When the stored model is not usable, the stored
    ``conversation.model_id`` is cleared to ``NULL`` so the *next* turn
    reads the catalog default cleanly — no per-turn-fails-forever UX trap —
    and the current turn falls back to the default entry.

    Telegram is catalog-ignorant on the write side (``/model`` only runs
    the structural parser, per ADR 2026-05-14 §7), so this is the single
    place where an unknown-but-well-formed stored ID gets surfaced to the
    user.

    Args:
        context: Resolved turn context with the stored ``model_id``.
        workspace_root: User's default workspace directory. Forwarded to
            provider adapters so native subprocesses write transcripts
            under the user workspace rather than the bot process directory.
            ``None`` for users without a workspace.

    Returns:
        A tuple of ``(selection, warning_text_or_None)``. When the auto-clear
        path fires, ``warning_text`` is a human-readable string the caller
        should send to the user before streaming. When the stored ID is
        valid, ``warning_text`` is ``None``.
    """
    selection = provider_or_default(context.model_id, workspace_root=workspace_root)
    if selection.warning is not None:
        warning = (
            f"Model <code>{context.model_id}</code> isn't usable: {selection.warning}. "
            f"Switching you back to the default ({selection.effective_model_id})."
        )
        async with async_session_maker() as session:
            await update_conversation_model(
                conversation_id=context.conversation_id,
                model_id=None,
                session=session,
            )
        logger.info(
            "TELEGRAM_MODEL_AUTO_CLEAR conversation_id=%s bad_model=%s",
            context.conversation_id,
            context.model_id,
        )
        return selection, warning
    return selection, None
