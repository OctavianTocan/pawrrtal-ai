"""Structured provider stream logging helpers."""

from __future__ import annotations

import logging
import uuid

from .base import StreamEvent

_SNIPPET_CHARS = 240


def log_provider_stream_event(
    logger: logging.Logger,
    *,
    provider: str,
    model: str,
    conversation_id: uuid.UUID,
    event: StreamEvent,
) -> None:
    """Emit a bounded, structured log for one provider ``StreamEvent``."""
    event_type = event.get("type", "unknown")
    if event_type in {"delta", "thinking", "error", "agent_terminated"}:
        content = str(event.get("content", ""))
        logger.info(
            "%s_STREAM_%s model=%s conversation_id=%s chars=%d snippet=%r",
            provider,
            str(event_type).upper(),
            model,
            conversation_id,
            len(content),
            _snippet(content),
        )
        return
    if event_type == "tool_use":
        tool_input = event.get("input")
        input_keys = sorted(tool_input.keys()) if isinstance(tool_input, dict) else []
        logger.info(
            "%s_STREAM_TOOL_USE model=%s conversation_id=%s tool_use_id=%s name=%s input_keys=%s",
            provider,
            model,
            conversation_id,
            event.get("tool_use_id"),
            event.get("name"),
            input_keys,
        )
        return
    if event_type == "tool_result":
        content = str(event.get("content", ""))
        logger.info(
            "%s_STREAM_TOOL_RESULT model=%s conversation_id=%s tool_use_id=%s chars=%d snippet=%r",
            provider,
            model,
            conversation_id,
            event.get("tool_use_id"),
            len(content),
            _snippet(content),
        )
        return
    if event_type == "usage":
        logger.info(
            "%s_STREAM_USAGE model=%s conversation_id=%s input_tokens=%s output_tokens=%s cost_usd=%s",
            provider,
            model,
            conversation_id,
            event.get("input_tokens"),
            event.get("output_tokens"),
            event.get("cost_usd"),
        )
        return
    logger.info(
        "%s_STREAM_EVENT model=%s conversation_id=%s type=%s keys=%s",
        provider,
        model,
        conversation_id,
        event_type,
        sorted(_string_keys(event)),
    )


def _string_keys(event: StreamEvent) -> list[str]:
    """Return string keys from a ``StreamEvent`` for stable log output."""
    return [key for key in event if isinstance(key, str)]


def _snippet(text: str) -> str:
    """Return a single-line, bounded preview for logs."""
    compact = " ".join(text.split())
    if len(compact) <= _SNIPPET_CHARS:
        return compact
    return f"{compact[:_SNIPPET_CHARS]}..."
