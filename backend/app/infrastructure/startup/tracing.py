"""Startup hook: OpenTelemetry tracing bootstrap."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.telemetry import setup_tracing
from app.infrastructure.lifecycle import startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=10)
async def start_tracing(app: FastAPI) -> None:
    """Install tracing instrumentation before outbound clients are used."""
    setup_tracing(app)
