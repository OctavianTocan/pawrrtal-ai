"""Shutdown hook: close the warm Antigravity API HTTP client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.lifecycle import shutdown_hook
from app.providers.agy_api.client import close_agy_api_client

if TYPE_CHECKING:
    from fastapi import FastAPI


@shutdown_hook(order=53)
async def close_agy_api_http_client(app: FastAPI) -> None:
    """Close the shared Antigravity API client after provider caches."""
    del app
    await close_agy_api_client()
