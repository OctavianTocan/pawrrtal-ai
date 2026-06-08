"""Turn context provider orchestration."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable
from pathlib import Path

from app.infrastructure.config import settings
from app.plugins.adapters.turn_context import (
    TurnContextProviderAdapter,
    TurnContextProviderContext,
)

from .types import ChatTurnInput

logger = logging.getLogger(__name__)


async def _run_turn_context_providers(turn_input: ChatTurnInput) -> str | None:
    """Run manifest-backed context providers and combine their results."""
    if not turn_input.turn_context_providers:
        return None

    results = await asyncio.gather(
        *[
            _run_single_provider(adapter=adapter, turn_input=turn_input)
            for adapter in turn_input.turn_context_providers
        ],
        return_exceptions=False,
    )

    context_items = [result for result in results if result is not None]
    if not context_items:
        return None
    return "# TURN CONTEXT\n\n" + "\n\n".join(context_items)


async def _run_single_provider(
    *,
    adapter: TurnContextProviderAdapter,
    turn_input: ChatTurnInput,
) -> str | None:
    """Run one provider with bounded failure handling."""
    logger.info(
        "TURN_CONTEXT_PROVIDER %s conversation_id=%s user_id=%s question=%s",
        adapter.log_name,
        turn_input.conversation_id,
        turn_input.user_id,
        turn_input.question,
    )
    try:
        async with asyncio.timeout(_timeout_seconds(adapter)):
            result = adapter.provider(
                TurnContextProviderContext(
                    conversation_id=turn_input.conversation_id,
                    user_id=turn_input.user_id,
                    question=turn_input.question,
                    workspace_root=turn_input.workspace_root or Path(),
                    draft_updater=turn_input.draft_updater,
                )
            )
            resolved = await _await_provider_result(result)
            if resolved is not None:
                logger.info(
                    "TURN_CONTEXT_PROVIDER_SUCCESS conversation_id=%s user_id=%s provider=%s question=%s result=%s",
                    turn_input.conversation_id,
                    turn_input.user_id,
                    adapter.log_name,
                    turn_input.question,
                    resolved,
                )
            return resolved
    except Exception:
        logger.exception(
            "TURN_CONTEXT_PROVIDER_ERR conversation_id=%s user_id=%s provider=%s question=%s",
            turn_input.conversation_id,
            turn_input.user_id,
            adapter.log_name,
            turn_input.question,
        )
        return None


async def _await_provider_result(value: Awaitable[str | None] | str | None) -> str | None:
    """Await async providers while tolerating sync test doubles."""
    if inspect.isawaitable(value):
        return await value
    return value


def _timeout_seconds(adapter: TurnContextProviderAdapter) -> float:
    """Return the bounded timeout for one context provider."""
    timeout = adapter.timeout_seconds or settings.turn_context_provider_timeout_seconds or 10
    return float(timeout)
