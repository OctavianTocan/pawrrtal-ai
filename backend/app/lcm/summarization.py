"""Provider-backed summarization helpers for LCM compaction."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

_log = logging.getLogger(__name__)

_FALLBACK_TRUNCATE_CHARS = 1500

_PROMPT_NORMAL = """\
You are a memory compressor for an AI assistant.  Summarize the following
conversation extract into a compact but lossless paragraph.  Preserve every
decision, fact, file name, error message, and instruction so the assistant can
reconstruct the full context from your summary alone.  Output the summary only
— no preamble, no commentary.

{turns}"""

_PROMPT_AGGRESSIVE = """\
Summarize the following conversation in one tight paragraph.  Keep only the
most important decisions, facts, and instructions.  Output the summary only.

{turns}"""


def _approx_tokens(text: str) -> int:
    """Rough token count: 4 characters is about 1 token."""
    return max(1, len(text) // 4)


def _format_turns(messages: list[dict[str, str]]) -> str:
    """Format chat messages as a plain-text transcript for the summary prompt."""
    parts: list[str] = []
    for message in messages:
        role = message.get("role", "").upper()
        content = message.get("content", "")
        if content:
            parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


def _resolve_summary_provider(model_id: str) -> Any:
    """Resolve a model provider only when compaction actually needs one."""
    from app.providers import resolve_llm  # noqa: PLC0415

    return resolve_llm(model_id)


async def _collect_stream(stream: AsyncIterator[Any]) -> str:
    """Consume a provider stream and return all concatenated delta text."""
    parts: list[str] = []
    async for event in stream:
        if event.get("type") != "delta":
            continue
        chunk = event.get("content") or ""
        if chunk:
            parts.append(chunk)
    return "".join(parts).strip()


async def _summarize(
    provider: Any,
    turns_text: str,
    user_id: uuid.UUID,
) -> tuple[str, str]:
    """Summarize a turn block, falling back to deterministic truncation."""
    for prompt_template, kind in (
        (_PROMPT_NORMAL, "normal"),
        (_PROMPT_AGGRESSIVE, "aggressive"),
    ):
        try:
            stream = provider.stream(
                question=prompt_template.format(turns=turns_text),
                conversation_id=uuid.uuid4(),
                user_id=user_id,
                history=None,
                tools=None,
                system_prompt=None,
            )
            text = await _collect_stream(stream)
            if text:
                return text, kind
        except Exception:
            _log.warning("LCM_SUMMARIZE_%s_FAILED", kind.upper(), exc_info=True)

    return turns_text[:_FALLBACK_TRUNCATE_CHARS], "fallback"
