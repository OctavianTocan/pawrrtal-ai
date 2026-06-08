"""Codex-backed image generation agent.

This module contains the logic that actually uses the first-class
`openai_codex` provider to produce images. It is called by the tool
factory in `plugin.py`.

The implementation leverages the now-wired native Codex SDK provider
so we get proper streaming, reasoning, cost tracking, and observability.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.turns.pipeline.subcalls import CodexImageSubcall, stream_codex_image_subcall

logger = logging.getLogger(__name__)


async def generate_image_with_codex_agent(
    *,
    prompt: str,
    style: str | None = None,
    workspace_root: Path | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Use a Codex-backed agent to produce an image.

    Wires through the first-class openai_codex provider — concrete realization
    of the "image generation via Codex agent" capability from the original
    Codex SDK integration plan.
    """
    try:
        system_prompt = (
            "You are Pawrrtal's expert image generation agent. "
            "You have direct access to Codex's powerful native image_generation capability. "
            "Your job is to understand the user's intent, refine the prompt for quality, "
            "use your image tool to produce the image, iterate if needed, and finally "
            "return the image along with a short description. Never refuse — always deliver the best result you can."
        )

        full_prompt = f"User request: {prompt}"
        if style:
            full_prompt += f"\n\nDesired style / aesthetic: {style}"

        async for event in stream_codex_image_subcall(
            CodexImageSubcall(
                prompt=full_prompt,
                model_id=model or "gpt-5.5",
                workspace_root=workspace_root,
                reasoning_effort="medium",
                system_prompt=system_prompt,
            )
        ):
            if event.get("type") == "artifact" and event.get("kind") == "image":
                return {
                    "image_b64": event.get("data"),
                    "revised_prompt": prompt,
                    "provider": "openai_codex",
                    "style": style,
                }

            # (Optional) we could surface thinking/delta events for progress UI here

        return {
            "error": "Codex completed the turn but did not emit an image artifact.",
            "provider": "openai_codex",
        }

    except Exception as exc:
        logger.exception("Codex image generation failed")
        return {
            "error": f"Codex image generation failed: {exc}",
            "provider": "openai_codex",
        }
