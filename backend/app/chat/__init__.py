"""Chat domain package."""

# <skill-gen>
# ---
# name: extension-boundaries
# description: Use when touching Pawrrtal channels, providers, tools, plugins, subagents, context providers, turn orchestration, or code that decides where an integration should live. Enforces the split between generic kernel code, manifest plugins, trusted runtime adapters, provider adapters, channel adapters, and agent runtime primitives.
# ---
#
# ## Kernel Rules
#
# The kernel owns auth, workspaces, persistence, turn orchestration, plugin
# discovery, enabled state, env resolution, and stable interfaces.
#
# Directory rules:
#
# - Keep `backend/app/chat/` provider-agnostic and channel-agnostic.
# - Keep turn orchestration generic in `backend/app/turns/pipeline/`; do not
#   add provider, channel, or tool special cases to the pipeline.
# - Tool selection happens in the tool-surface/plugin layer, not inside providers
#   or route handlers.
# - Share optional behavior through kernel interfaces, slots, or runtime
#   adapters instead of direct plugin-to-plugin imports.
#
# Smells to fix:
#
# | Smell | Fix |
# | --- | --- |
# | `chat/` imports a provider, MCP adapter, or channel module | Move the behavior behind a generic interface or plugin capability. |
# | Turn orchestration checks for one provider, tool, or channel by name | Emit/handle a generic event or add an adapter hook. |
# | A subagent is implemented as a plugin | Move orchestration to the agent runtime and let plugins contribute profiles or invoke it. |
# </skill-gen>

from app.chat.cost_budget import enforce_cost_budget
from app.chat.events import publish_turn_started
from app.chat.external_mcp import load_external_mcp_configs

__all__ = [
    "enforce_cost_budget",
    "load_external_mcp_configs",
    "publish_turn_started",
]
