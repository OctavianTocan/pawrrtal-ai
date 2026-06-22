"""Manifest-backed Pawrrtal plugin platform."""

# <skill-gen>
# ---
# name: extension-boundaries
# description: Use when touching Pawrrtal channels, providers, tools, plugins, subagents, context providers, turn orchestration, or code that decides where an integration should live. Enforces the split between generic kernel code, manifest plugins, trusted runtime adapters, provider adapters, channel adapters, and agent runtime primitives.
# ---
#
# ## Plugin Platform
#
# A plugin manifest is `backend/plugins/<plugin_id>/plugin.json`. It is
# declarative metadata: capabilities, env requirements, validation commands,
# permissions, slots, and entrypoints.
#
# Plugin runtime code lives in `backend/app/plugins/`. It is trusted host code
# plus bundled Python implementations that a manifest may activate.
#
# A slot is a named extension point where multiple plugins can fit, such as
# `tasks`, `web_search`, `channel:telegram`, `provider:models`, or
# `conversation_memory`.
#
# Before adding optional behavior:
#
# 1. Name the capability type: `provider`, `channel`, `cli_tool`, `python_tool`,
#    `turn_context_provider`, `conversation_memory`, `agent_runtime`,
#    `agent_profile`, `router`, `settings`, or `scheduler`.
# 2. Name the slot if users may choose among multiple implementations.
# 3. Decide whether the code is generic kernel code or a trusted bundled
#    adapter.
# 4. Add or update the manifest first when the behavior is optional.
# 5. Declare env requirements in the manifest. Use `user_workspace` or
#    `workspace` scope when values must be overridable per workspace/user.
# 6. Keep enabled/disabled behavior explicit. Disabled plugins must not
#    advertise tools, providers, channels, or context providers.
# 7. Add tests at the interface: manifest validation, registry/slot resolution,
#    enabled-state behavior, env gating, and the runtime adapter.
# 8. Verify through Paw when the behavior affects a user-visible flow.
#
# Plugin smells to fix:
#
# | Smell | Fix |
# | --- | --- |
# | Plugin code reads `os.environ` directly for user/workspace settings | Declare env in the manifest and use the plugin env resolver. |
# | A plugin is always on because it exists on disk | Add enabled-state tests and make the manifest default intentional. |
# | Plugins import each other directly | Share behavior through kernel interfaces, slots, or runtime adapters. |
# </skill-gen>
