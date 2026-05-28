"""Plugin manifest for Codex-driven image generation.

Importing this module registers the plugin. The actual tool is produced
by a factory so it can be bound to the current workspace / user context.

This is the modern (post-2026-05 plugin registry) implementation of the
"image generation via Codex agent" capability described in the original
Codex SDK integration plan.
"""

from __future__ import annotations

from app.core.plugins import (
    EnvKeySpec,
    Plugin,
)
from app.core.plugins.registry import register_plugin
from app.plugins.openai_codex_image_gen.plugin import make_codex_image_tool

codex_image_plugin = Plugin(
    id="openai_codex_image_gen",
    name="Codex Image Generation",
    description=(
        "Generate high-quality images by delegating to a short-lived Codex agent "
        "powered by the official openai_codex SDK (native threads + image tool)."
    ),
    env_keys=(
        EnvKeySpec(
            name="OPENAI_CODEX_OAUTH_TOKEN",
            label="Codex OAuth Token (optional override)",
            required=False,
            help_url="https://github.com/openai/codex",
        ),
    ),
    tool_factories=(make_codex_image_tool,),
)

register_plugin(codex_image_plugin)

__all__ = ["codex_image_plugin"]
