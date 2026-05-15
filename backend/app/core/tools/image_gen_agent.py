"""Agent-loop adapter for the gpt-image-2 / Codex OAuth image-generation tool.

Exposes :func:`make_image_gen_tool`, which returns an :class:`AgentTool`
the agent can call as ``generate_image``.  The generated PNG is written to
the user's workspace under ``generated_images/<timestamp>_<slug>.png`` and
the tool result reports the saved path so the user (and the LLM) know where
to find it.

The actual HTTP call to the Codex Responses backend lives in the shared
core (:mod:`app.core.tools.image_gen`) — this module only handles schema
definition and the async wrapper the loop invokes.

Usage::

    from app.core.tools.image_gen_agent import make_image_gen_tool

    tools = [make_image_gen_tool(workspace_root=path, user_id=user.id)]
    context = AgentContext(system_prompt=..., messages=..., tools=tools)
"""

from __future__ import annotations

import datetime
import json
import re
import uuid
from pathlib import Path

from app.core.agent_loop.types import AgentTool
from app.core.keys import resolve_api_key
from app.core.tools.image_gen import generate_image_via_codex, resolve_codex_oauth_token

_TOOL_NAME = "generate_image"

_TOOL_DESCRIPTION = """\
Generate an image from a text description using gpt-image-2 via the \
OpenAI Codex Responses API.

The image is saved to the workspace under `generated_images/` and \
the saved path is returned so you can reference or share it. \
Use descriptive, detailed prompts for best results. \
Requires an active Codex OAuth session — no separate OpenAI API key needed.\
"""

_PARAMETERS: dict = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": (
                "Detailed natural-language description of the image to generate. "
                "Include style, colours, composition, and mood for best results."
            ),
        },
        "size": {
            "type": "string",
            "description": (
                "Image dimensions. Supported values: "
                '"1024x1024" (square, default), '
                '"1024x1536" (portrait), '
                '"1536x1024" (landscape).'
            ),
            "default": "1024x1024",
            "enum": ["1024x1024", "1024x1536", "1536x1024"],
        },
        "quality": {
            "type": "string",
            "description": (
                'Generation quality. "low" is fastest; '
                '"medium" balances speed and detail (default); '
                '"high" produces the most detailed output.'
            ),
            "default": "medium",
            "enum": ["low", "medium", "high"],
        },
        "filename": {
            "type": "string",
            "description": (
                "Optional base filename (without extension). "
                "If omitted a timestamped slug derived from the prompt is used."
            ),
        },
    },
    "required": ["prompt"],
}

# Characters that are safe in filenames (ASCII letters, digits, hyphen, underscore).
_SAFE_CHARS = re.compile(r"[^a-z0-9_-]")

_MAX_SLUG_LEN = 40


def _make_slug(prompt: str) -> str:
    """Derive a short filesystem-safe slug from the prompt."""
    lower = prompt.lower()
    slug = _SAFE_CHARS.sub("_", lower)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:_MAX_SLUG_LEN] or "image"


def make_image_gen_tool(
    *,
    workspace_root: Path,
    workspace_id: uuid.UUID | None = None,
) -> AgentTool:
    """Return an :class:`AgentTool` that generates images via Codex OAuth.

    Args:
        workspace_root: The user's workspace directory.  Generated images are
            saved here under ``generated_images/``.
        workspace_id: Active workspace UUID, used to resolve the
            ``OPENAI_CODEX_OAUTH_TOKEN`` workspace override if set.

    Returns:
        A configured :class:`AgentTool` ready to append to
        ``AgentContext.tools``.
    """

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        prompt = str(kwargs.get("prompt") or "")
        size = str(kwargs.get("size") or "1024x1024")
        quality = str(kwargs.get("quality") or "medium")
        custom_filename = kwargs.get("filename")

        if not prompt:
            return json.dumps({"error": "prompt is required"})

        # Resolve Codex OAuth token: workspace override → auth.json fallback.
        override_token: str | None = None
        if workspace_id is not None:
            override_token = resolve_api_key(workspace_id, "OPENAI_CODEX_OAUTH_TOKEN")

        try:
            oauth_token = resolve_codex_oauth_token(override_token)
        except RuntimeError as exc:
            return json.dumps({"error": str(exc)})

        # Generate image bytes.
        try:
            image_bytes = await generate_image_via_codex(
                prompt,
                oauth_token=oauth_token,
                size=size,
                quality=quality,
            )
        except Exception as exc:
            return json.dumps({"error": f"Image generation failed: {exc}"})

        # Persist to workspace.
        ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%dT%H%M%S")
        if custom_filename:
            slug = _SAFE_CHARS.sub("_", str(custom_filename).lower()).strip("_") or "image"
        else:
            slug = _make_slug(prompt)
        filename = f"{ts}_{slug}.png"

        out_dir = workspace_root / "generated_images"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename
        out_path.write_bytes(image_bytes)

        relative = out_path.relative_to(workspace_root)
        return json.dumps(
            {
                "status": "success",
                "path": str(relative),
                "size_bytes": len(image_bytes),
                "dimensions": size,
                "quality": quality,
                "message": f"Image saved to {relative}",
            }
        )

    return AgentTool(
        name=_TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        parameters=_PARAMETERS,
        execute=_execute,
    )
