"""Shutdown hook: close warm Codex provider app-server clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.lifecycle import shutdown_hook
from app.providers.factory import close_openai_codex_provider_cache

if TYPE_CHECKING:
    from fastapi import FastAPI


@shutdown_hook(order=54)
async def close_codex_provider_cache(app: FastAPI) -> None:
    """Close cached Codex providers after in-flight thread-id writes drain."""
    del app
    await close_openai_codex_provider_cache()
