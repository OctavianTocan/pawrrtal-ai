"""Pre-turn context provider orchestration."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.agents.plugins.types import PreTurnHook, PreTurnHookContext
from app.infrastructure.config import settings

from .types import ChatTurnInput

logger = logging.getLogger(__name__)


async def _run_pre_turn_hooks(turn_input: ChatTurnInput) -> str | None:
    # --- Pre-turn hooks ---
    if not turn_input.pre_turn_hooks:
        return None

    async def _run_single_hook(hook: PreTurnHook) -> str | None:
        hook_name = hook.__name__
        logger.info(
            "PRE_TURN_HOOK %s conversation_id=%s user_id=%s question=%s",
            hook_name,
            turn_input.conversation_id,
            turn_input.user_id,
            turn_input.question,
        )
        try:
            async with asyncio.timeout(settings.pre_turn_hook_timeout_seconds or 10):
                result = await hook(
                    PreTurnHookContext(
                        conversation_id=turn_input.conversation_id,
                        user_id=turn_input.user_id,
                        question=turn_input.question,
                        workspace_root=turn_input.workspace_root or Path(),
                        draft_updater=turn_input.draft_updater,
                    )
                )
                if result is not None:
                    logger.info(
                        "PRE_TURN_HOOK_SUCCESS %s conversation_id=%s user_id=%s hook_name=%s question=%s result=%s",
                        hook_name,
                        turn_input.conversation_id,
                        turn_input.user_id,
                        hook_name,
                        turn_input.question,
                        result,
                    )
                return result
        except Exception:
            logger.exception(
                "PRE_TURN_HOOK_ERR %s conversation_id=%s user_id=%s hook_name=%s question=%s",
                hook_name,
                turn_input.conversation_id,
                turn_input.user_id,
                hook_name,
                turn_input.question,
            )
            return None

    results = await asyncio.gather(
        *[_run_single_hook(hook) for hook in turn_input.pre_turn_hooks],
        return_exceptions=False,
    )

    pre_turn_added_context = [res for res in results if res is not None]
    if not pre_turn_added_context:
        return None

    return "# PRE-TURN CONTEXT\n\n" + "\n\n".join(pre_turn_added_context)
