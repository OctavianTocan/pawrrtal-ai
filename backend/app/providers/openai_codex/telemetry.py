"""Telemetry helpers for the native Codex provider."""

from __future__ import annotations

import logging
import time
import uuid

logger = logging.getLogger(__name__)


def log_codex_phase(
    conversation_id: uuid.UUID,
    phase: str,
    started_at: float,
    **fields: object,
) -> None:
    """Log one timed Codex provider phase."""
    suffix = " ".join(f"{key}={value}" for key, value in fields.items())
    message = "CODEX_PROVIDER_PHASE conversation_id=%s phase=%s duration_ms=%.1f"
    if suffix:
        message = f"{message} {suffix}"
    logger.info(message, conversation_id, phase, (time.perf_counter() - started_at) * 1000.0)
