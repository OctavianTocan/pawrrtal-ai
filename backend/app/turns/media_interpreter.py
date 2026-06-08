"""Generic media interpretation helpers used before a main turn."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.providers.selection import require_provider

_IMAGE_SYSTEM_PROMPT = (
    "You are a visual understanding sub-agent for Pawrrtal. Describe the attached "
    "image(s) for another agent. Be factual, concise, and include any visible "
    "text, UI state, objects, people, diagrams, errors, or counts that could "
    "matter to the user's request. Do not answer the user's request; only "
    "describe the image evidence."
)


async def describe_images_for_turn(
    *,
    images: list[dict[str, str]],
    model_id: str,
    workspace_root: Path | None,
    user_id: uuid.UUID,
    user_prompt: str,
    fallback_prompt: str,
) -> str:
    """Stream a single image-description turn and return its text."""
    selection = require_provider(model_id, workspace_root=workspace_root)
    question = _image_question(user_prompt, fallback_prompt=fallback_prompt)
    chunks: list[str] = []
    async for event in selection.provider.stream(
        question,
        uuid.uuid4(),
        user_id,
        history=[],
        tools=None,
        system_prompt=_IMAGE_SYSTEM_PROMPT,
        reasoning_effort="minimal",
        images=images,
    ):
        if event.get("type") == "error":
            raise RuntimeError(str(event.get("content") or "image sub-agent failed"))
        if event.get("type") in {"delta", "message"}:
            content = str(event.get("content") or "")
            if content:
                chunks.append(content)
    description = "".join(chunks).strip()
    if not description:
        raise RuntimeError("image sub-agent returned an empty description")
    return description


def _image_question(user_prompt: str, *, fallback_prompt: str) -> str:
    """Build the image-analysis request for the sub-agent."""
    trimmed = user_prompt.strip()
    if not trimmed:
        return fallback_prompt
    return f"{fallback_prompt}\n\nUser text or caption:\n{trimmed}"
