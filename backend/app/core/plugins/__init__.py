"""Plugin registry — additive integrations that contribute agent tools.

A plugin is a Python package under ``backend/app/integrations/<id>/``
that exports a :class:`Plugin` object describing one integration.
Plugins extend the agent's capabilities without modifying core code:
each plugin contributes one or more tool factories plus a list of
workspace-scoped env keys it depends on.

Design notes:

* **Additive only.** Core tools (workspace files, web search, image
  generation, artifact rendering, message delivery) stay hardcoded in
  :func:`app.core.agent_tools.build_agent_tools`. The registry append
  happens *after* core tool composition. We avoid a refactor whose only
  payoff would be uniformity for its own sake.
* **Tools only, v1.** Plugin-registered channels, providers, hooks, and
  HTTP routes are out of scope. The seams exist (``Channel`` protocol,
  ``LLMProvider``) and can grow later without changing this API.
* **In-process, first-party.** Plugins are imported Python packages,
  not dynamically-loaded artifacts. Discovery happens through
  ``app.integrations.__init__`` importing each subpackage, which in
  turn calls :func:`register_plugin`. No manifest JSON, no hot reload.
* **Capability gating via ``is_activated``.** A plugin's tools only
  reach the agent when its prerequisites resolve in the current
  :class:`ToolContext` — typically "the workspace has a value
  configured for every env key the plugin declares". The default
  implementation handles that case; plugins can override for more
  complex predicates.

See ``frontend/content/docs/handbook/decisions/2026-05-15-plugin-system-and-notion-integration.mdx``
for the design rationale.
"""

from app.core.plugins.registry import all_plugins, register_plugin
from app.core.plugins.types import EnvKeySpec, Plugin, ToolContext, ToolFactory

__all__ = [
    "EnvKeySpec",
    "Plugin",
    "ToolContext",
    "ToolFactory",
    "all_plugins",
    "register_plugin",
]
