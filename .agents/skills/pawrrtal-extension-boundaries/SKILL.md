---
name: pawrrtal-extension-boundaries
description: Use when touching Pawrrtal channels, providers, tools, plugins, subagents, context providers, turn orchestration, or code that decides where an integration should live. Enforces the split between generic kernel code, manifest plugins, trusted runtime adapters, provider adapters, channel adapters, and agent runtime primitives.
---

# Pawrrtal Extension Boundaries

Use this before changing backend extension code. The goal is a thin generic
kernel with optional pieces installed as plugins.

## Vocabulary

- **Kernel**: generic runtime code that owns auth, workspaces, persistence,
  turn orchestration, plugin discovery, enabled state, env resolution, and
  stable interfaces.
- **Plugin manifest**: `backend/plugins/<plugin_id>/plugin.json`. This is
  declarative metadata: capabilities, env requirements, validation commands,
  permissions, slots, and entrypoints.
- **Plugin runtime**: `backend/app/plugins/`. This is trusted host code plus
  bundled Python implementations that a manifest may activate.
- **Provider adapter**: code that talks to one model provider or provider CLI.
  It belongs under `backend/app/providers/` or behind a provider plugin
  capability.
- **Channel adapter**: code that talks to one user surface such as Telegram or
  Google Chat. It belongs under `backend/app/channels/` or behind a channel
  plugin capability.
- **Tool adapter**: code that exposes one agent tool. Tool selection happens in
  the tool-surface/plugin layer, not inside providers.
- **Subagent**: an agent-runtime primitive. Plugins may invoke subagents or
  contribute agent profiles, but plugins do not implement the subagent kernel.
- **Slot**: a named extension point where multiple plugins can fit, such as
  `tasks`, `web_search`, `channel:telegram`, `provider:models`, or
  `conversation_memory`.

## Directory Rules

- Put bundled plugin manifests in `backend/plugins/<plugin_id>/plugin.json`.
- Put trusted plugin host code and bundled implementations in
  `backend/app/plugins/`.
- Put provider-specific code in `backend/app/providers/<provider>/`.
- Put channel-specific code in `backend/app/channels/<channel>/`.
- Keep `backend/app/chat/` provider-agnostic and channel-agnostic.
- Keep `backend/app/conversations/` free of provider-specific helpers.
- Keep `backend/app/channels/turn_orchestrator/` free of provider, channel, and
  tool special cases.
- Do not make providers import tool modules. Providers translate generic
  `AgentTool` objects into SDK-specific formats.
- Do not make channels import provider internals. Channels choose a model and
  call the generic turn runner.
- Do not make plugins import each other directly. Share behavior through
  kernel interfaces, slots, or runtime adapters.

## Before Adding Code

1. Name the capability type: `provider`, `channel`, `cli_tool`,
   `python_tool`, `turn_context_provider`, `conversation_memory`,
   `agent_runtime`, `agent_profile`, `router`, `settings`, or `scheduler`.
2. Name the slot if users may choose among multiple implementations.
3. Decide whether the code is generic kernel code or a trusted bundled adapter.
4. Add or update the manifest first when the behavior is optional.
5. Declare env requirements in the manifest. Use `user_workspace` or
   `workspace` scope when values must be overridable per workspace/user.
6. Keep enabled/disabled behavior explicit. Disabled plugins must not advertise
   tools, providers, channels, or context providers.
7. Add tests at the interface: manifest validation, registry/slot resolution,
   enabled-state behavior, env gating, and the runtime adapter.
8. Verify through Paw when the behavior affects a user-visible flow.

## Smells To Fix

| Smell | Fix |
| --- | --- |
| `chat/` imports a provider, MCP adapter, or channel module | Move the behavior behind a generic interface or plugin capability. |
| `conversations/` contains `gemini_*`, `codex_*`, or another provider name | Move it to the provider package and expose a generic history adapter. |
| `turn_orchestrator/` checks for one provider, tool, or channel by name | Emit/handle a generic event or add an adapter hook. |
| A provider imports tool factories | Pass generic `AgentTool` values into the provider and translate there. |
| A channel formats tools, keyboards, or command output ad hoc | Move reusable formatting to channel runtime helpers or a channel adapter. |
| Plugin code reads `os.environ` directly for user/workspace settings | Declare env in the manifest and use the plugin env resolver. |
| A plugin is always on because it exists on disk | Add enabled-state tests and make the manifest default intentional. |
| A subagent is implemented as a plugin | Move orchestration to the agent runtime and let plugins contribute profiles or invoke it. |

## Verification

Use the Paw CLI as the operator surface:

```bash
paw plugins spec --json
paw plugins list --json
paw plugins capabilities search --slot tasks --json
paw plugins slots list --json
paw plugins validate backend/plugins/<plugin_id>/plugin.json --source bundled --json
```

For runtime changes, add focused tests and then run the relevant gates:

```bash
cd backend && uv run pytest tests/test_plugin_discovery.py tests/test_plugin_tools.py
cd backend && uv run pytest tests/test_channel_plugins.py tests/test_provider_plugins.py
paw verify chat-roundtrip --json
```

Run broader CI gates before claiming the PR is ready.
