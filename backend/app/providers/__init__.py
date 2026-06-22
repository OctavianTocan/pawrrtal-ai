"""Provider package — public surface for the AI provider abstraction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AILLM, ReasoningEffort, StreamEvent

if TYPE_CHECKING:
    from .catalog import first_catalog_model
    from .claude_code_pty import ClaudeCodePtyLLM, ClaudeCodePtyLLMConfig
    from .factory import resolve_llm
    from .xai import XaiLLM

# <skill-gen>
# ---
# name: extension-boundaries
# description: Use when touching Pawrrtal channels, providers, tools, plugins, subagents, context providers, turn orchestration, or code that decides where an integration should live. Enforces the split between generic kernel code, manifest plugins, trusted runtime adapters, provider adapters, channel adapters, and agent runtime primitives.
# ---
#
# ## Provider Adapters
#
# A provider adapter talks to one model provider or provider CLI. It belongs
# under `backend/app/providers/` or behind a provider plugin capability.
#
# Provider adapters should:
#
# - Translate generic `AgentTool` objects into SDK-specific formats.
# - Avoid importing tool modules or tool factories directly.
# - Keep channel-specific formatting and command output out of providers.
# - Keep provider-specific history/session code inside the provider package and
#   expose generic adapters to the rest of the app.
#
# Smells to fix:
#
# | Smell | Fix |
# | --- | --- |
# | A provider imports tool factories | Pass generic `AgentTool` values into the provider and translate there. |
# | A channel imports provider internals | Route through the generic turn runner or provider factory. |
#
# ## Verification
#
# Use Paw as the operator surface. From the repo root, prefer `just paw`; from
# `backend/`, use `uv run paw`.
#
# ```bash
# just paw plugins spec --json
# just paw plugins list --json
# just paw plugins capabilities search --slot tasks --json
# just paw plugins slots list --json
# just paw plugins validate backend/plugins/<plugin_id>/plugin.json --source bundled --json
# ```
#
# For runtime changes, add focused tests and then run the relevant gates:
#
# ```bash
# cd backend && uv run pytest tests/test_plugin_discovery.py tests/test_plugin_tools.py
# cd backend && uv run pytest tests/test_channel_plugins.py tests/test_provider_plugins.py
# cd backend && uv run paw verify chat-roundtrip --json
# ```
#
# Run broader CI gates before claiming the PR is ready.
# </skill-gen>

__all__ = [
    "AILLM",
    "ClaudeCodePtyLLM",
    "ClaudeCodePtyLLMConfig",
    "ReasoningEffort",
    "StreamEvent",
    "XaiLLM",
    "first_catalog_model",
    "resolve_llm",
]


def __getattr__(name: str) -> object:
    """Load provider implementations lazily.

    Importing ``app.providers.base`` should not load SDK-backed provider
    modules. The CLI and schemas use the base types frequently, and eager
    imports used to leak LiteLLM warnings into unrelated JSON commands.
    """
    if name == "first_catalog_model":
        from .catalog import first_catalog_model  # noqa: PLC0415

        return first_catalog_model
    if name == "resolve_llm":
        from .factory import resolve_llm  # noqa: PLC0415

        return resolve_llm
    if name in {"ClaudeCodePtyLLM", "ClaudeCodePtyLLMConfig"}:
        from .claude_code_pty import (  # noqa: PLC0415
            ClaudeCodePtyLLM,
            ClaudeCodePtyLLMConfig,
        )

        return {
            "ClaudeCodePtyLLM": ClaudeCodePtyLLM,
            "ClaudeCodePtyLLMConfig": ClaudeCodePtyLLMConfig,
        }[name]
    if name == "XaiLLM":
        from .xai import XaiLLM  # noqa: PLC0415

        return XaiLLM
    raise AttributeError(name)
