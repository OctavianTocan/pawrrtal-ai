"""Provider resolution helper with auto-clear safety net.

Extracted from :mod:`app.integrations.telegram.bot` to keep that module's
fan-out under the sentrux god-file threshold (15). The catalog / model-id
machinery used by this helper accounts for ~4 of bot.py's import edges;
hoisting it out concentrates them in one place.

See ``_resolve_provider_with_auto_clear`` for the auto-clear contract
(originally documented inline in ``bot.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.providers import resolve_llm
from app.core.providers.base import AILLM
from app.core.providers.catalog import default_model, require_known
from app.core.providers.model_id import InvalidModelId, UnknownModelId
from app.crud.channel import update_conversation_model
from app.db import async_session_maker
from app.integrations.telegram.handlers import TelegramTurnContext

logger = logging.getLogger(__name__)


async def resolve_provider_with_auto_clear(
    context: TelegramTurnContext,
    *,
    workspace_root: Path | None = None,
) -> tuple[AILLM, str | None]:
    """Resolve a provider for ``context.model_id`` with an auto-clear safety net.

    On either :class:`InvalidModelId` (string doesn't parse) or
    :class:`UnknownModelId` (parses but isn't in the catalog), the stored
    ``conversation.model_id`` is cleared to ``NULL`` so the *next* turn
    reads :func:`catalog.default_model` cleanly — no per-turn-fails-forever
    UX trap — and the current turn falls back to the catalog default.

    Telegram is catalog-ignorant on the write side (``/model`` only runs
    the structural parser, per ADR 2026-05-14 §7), so this is the single
    place where an unknown-but-well-formed stored ID gets surfaced to the
    user.

    Args:
        context: Resolved turn context with the stored ``model_id``.
        workspace_root: User's default workspace directory. Forwarded to
            ``resolve_llm`` so the Claude SDK subprocess writes its
            transcripts under the user workspace rather than the bot
            process directory. ``None`` for users without a workspace
            (pre-onboarding); the provider still runs isolated via
            ``setting_sources=[]`` regardless.

    Returns:
        A tuple of ``(provider, warning_text_or_None)``. When the auto-clear
        path fires, ``warning_text`` is a human-readable string the caller
        should send to the user before streaming. When the stored ID is
        valid, ``warning_text`` is ``None``.
    """
    try:
        require_known(context.model_id)
        provider = resolve_llm(
            context.model_id,
            user_id=context.nexus_user_id,
            workspace_root=workspace_root,
        )
    except (InvalidModelId, UnknownModelId) as exc:
        fallback_id = default_model().id
        warning = (
            f"Model <code>{context.model_id}</code> isn't usable: {exc}. "
            f"Switching you back to the default ({fallback_id})."
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
        provider = resolve_llm(
            fallback_id,
            user_id=context.nexus_user_id,
            workspace_root=workspace_root,
        )
        return provider, warning
    return provider, None
