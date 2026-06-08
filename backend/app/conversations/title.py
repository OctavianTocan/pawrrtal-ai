"""Conversation title generation through provider selection."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.providers.selection import default_model_id, require_provider

TITLE_GENERATION_SLOT = "conversation.title.generate"
_TITLE_SYSTEM_PROMPT = (
    "You generate concise conversation titles. Return only the title text, "
    "with no quotes or explanation."
)


def title_generation_prompt(first_message: str) -> str:
    """Return the provider prompt for the conversation title task."""
    return (
        "Generate a short title (max 8 words) for the conversation based on "
        "this first message: " + first_message + ". Return only the title, nothing else."
    )


async def generate_conversation_title_text(
    *,
    first_message: str,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    model_id: str | None = None,
    workspace_root: Path | None = None,
) -> str:
    """Run the internal title task with the selected provider."""
    selection = require_provider(model_id or default_model_id(), workspace_root=workspace_root)
    chunks = [
        event.get("content", "")
        async for event in selection.provider.stream(
            title_generation_prompt(first_message),
            conversation_id,
            user_id,
            history=[],
            tools=None,
            system_prompt=_TITLE_SYSTEM_PROMPT,
        )
        if event.get("type") == "delta"
    ]
    return "".join(chunks).strip()
