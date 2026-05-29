"""Shutdown hook: stop OpenTelemetry tracing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.lifecycle import shutdown_hook
from app.infrastructure.telemetry import shutdown_tracing

if TYPE_CHECKING:
    from fastapi import FastAPI


@shutdown_hook(order=10)
async def stop_tracing(app: FastAPI) -> None:
    """Flush and stop tracing providers."""
    del app
    shutdown_tracing()
