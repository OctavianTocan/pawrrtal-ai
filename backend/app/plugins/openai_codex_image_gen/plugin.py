"""Tool factory and plugin registration for Codex-driven image generation.

This follows the exact modern pattern used by the notion plugin
(tool_factories + ToolContext) and is a pure tool plugin (no pre-turn hooks).
"""

from __future__ import annotations

import json
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.plugins.types import ToolContext
from app.plugins.openai_codex_image_gen.codex_image_agent import (
    generate_image_with_codex_agent,
)

CODEX_IMAGE_TOOL_NAME = "generate_image_via_codex"
CODEX_IMAGE_TOOL_DESCRIPTION = (
    "Generate an image by spinning up a short-lived Codex agent (powered by the "
    "official openai_codex SDK). The agent receives a carefully engineered prompt, "
    "uses Codex's native image_generation capability, and returns the result. "
    "Excellent for complex, iterative, or high-quality image requests."
)


def make_codex_image_tool(ctx: ToolContext) -> AgentTool:
    """Factory that produces the Codex image generation tool bound to this context."""

    async def _execute(
        _tool_call_id: str, prompt: str, style: str | None = None, **kwargs: Any
    ) -> str:
        result = await generate_image_with_codex_agent(
            prompt=prompt,
            style=style,
            workspace_root=ctx.workspace_root,
            # Future: pass model preference, user_id, etc. from ctx when needed
        )

        if "error" in result:
            return json.dumps({"error": result["error"], "provider": "openai_codex"})

        # Return a compact JSON payload the agent / UI can consume.
        # The artifact system will normally pick up image artifacts separately,
        # but returning the data here makes the tool immediately useful.
        return json.dumps(
            {
                "image": result.get("image_b64") or result.get("data"),
                "revised_prompt": result.get("revised_prompt", prompt),
                "style": style,
                "provider": "openai_codex",
            },
            ensure_ascii=False,
        )

    return AgentTool(
        name=CODEX_IMAGE_TOOL_NAME,
        description=CODEX_IMAGE_TOOL_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the image the user wants.",
                },
                "style": {
                    "type": "string",
                    "description": "Optional style or aesthetic guidance (e.g. 'cinematic, volumetric lighting, in the style of Greg Rutkowski').",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        execute=_execute,
    )
