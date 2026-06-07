"""Shutdown hook: close provider-owned process caches."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.lifecycle import shutdown_hook
from app.providers.factory import close_provider_caches

if TYPE_CHECKING:
    from fastapi import FastAPI


@shutdown_hook(order=54)
async def close_provider_process_caches(app: FastAPI) -> None:
    """Close cached provider clients before the process exits."""
    del app
    await close_provider_caches()
