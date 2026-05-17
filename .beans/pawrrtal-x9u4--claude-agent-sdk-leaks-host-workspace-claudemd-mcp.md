---
# pawrrtal-x9u4
title: Claude Agent SDK leaks host workspace (CLAUDE.md, .mcp.json, .claude/settings.json) into chat sessions
status: in-progress
type: bug
priority: critical
created_at: 2026-05-17T09:19:48Z
updated_at: 2026-05-17T09:28:03Z
---

## Problem

The Claude Agent SDK provider runs without an isolated `cwd` and with `setting_sources=["project"]` enabled by default. This causes every chat turn that uses a Claude model to ingest files from the **backend host's filesystem** rather than the user's workspace:

- Repo-root `CLAUDE.md` is loaded into the system prompt (in addition to the `WorkspaceContext`-injected one — duplicate read of the *wrong* project)
- Repo-root `.claude/settings.json` is loaded, including its hooks (e.g. the `beans prime` SessionStart hook)
- Repo-root `.mcp.json` is auto-discovered, registering the developer's local MCP servers (context7, deepwiki, stagehand-docs) as additional tool surfaces visible to the agent

## Root cause

`backend/app/core/providers/factory.py:75-79` constructs `ClaudeLLMConfig` without `cwd`, so the SDK falls back to the uvicorn process cwd. `backend/app/core/providers/claude_provider.py:435` then passes `setting_sources=["project"]` whenever `workspace_context_enabled=True` (the default per `backend/app/core/config.py:234`). With `cwd` defaulting to the backend dir, "project" resolves to the backend repo instead of the user workspace.

`backend/app/core/governance/workspace_context.py:118` describes this as "defence in depth" — but the SDK is reading a different directory than `WorkspaceContext` does, so it's defence against the wrong threat model. It's a leak, not a redundancy.

## Authoritative reference

From the installed SDK (`claude_agent_sdk/types.py:1650`):

```
setting_sources: list[SettingSource] | None = None
- "user"    — Global user settings (~/.claude/settings.json).
- "project" — Project settings (.claude/settings.json).
- "local"   — Local settings (.claude/settings.local.json).

When None, all sources are loaded (matches CLI defaults). Pass []
to disable filesystem settings (SDK isolation mode). Must include
"project" to load CLAUDE.md files.
```

`setting_sources=[]` is the SDK's documented isolation mode. We are not using it.

## Fix

Three changes:

- [x] `backend/app/core/providers/factory.py`: accept `workspace_root: Path` on `resolve_llm` and pass `cwd=str(workspace_root)` into `ClaudeLLMConfig`
- [x] `backend/app/core/providers/claude_provider.py:435`: set `setting_sources=[]` unconditionally for the chat surface (drop the `workspace_context_enabled` branch; `WorkspaceContext` already injects workspace `CLAUDE.md` into the system prompt from the correct root)
- [x] `backend/app/api/chat.py:225`: hoist the `root = _require_workspace_root(...)` call above `resolve_llm` and pass it through
- [x] Update the docstring at `claude_provider.py:425-435` so future readers understand why setting sources are off
- [x] Add regression tests: two new tests in `test_providers_and_schemas.py` verify `workspace_root` propagates to `cwd`; updated `test_default_options_lock_down_tools_and_settings` to assert `setting_sources == []`
- [ ] Manual smoke: hit /api/chat with a Claude model, verify no `mcp__context7__*` etc. tools surface in the trace and that the prompt doesn't reference the repo's CLAUDE.md content


## Summary of Changes

Three-file patch closing the workspace-isolation leak:

- `backend/app/core/providers/claude_provider.py`: `setting_sources` is now hard-coded to `[]` (the SDK's documented isolation mode). The previous `["project"]` branch was reading the backend repo's `CLAUDE.md`, `.claude/settings.json`, and `.mcp.json` because `cwd` was unset. Workspace `CLAUDE.md` is still injected via `channels/turn_runner._workspace_system_prompt` from the correct user workspace root.
- `backend/app/core/providers/factory.py`: `resolve_llm` now accepts optional `workspace_root: Path` and passes it into `ClaudeLLMConfig.cwd`. Non-chat callers (LCM, event-bus, telegram) keep `cwd=None` — they rely on `setting_sources=[]` alone.
- `backend/app/api/chat.py`: hoisted `_require_workspace_root(...)` above `resolve_llm` so the chat surface always passes `workspace_root`.

Tests: 96/96 green across `test_claude_provider.py`, `test_providers_and_schemas.py`, `test_chat_api.py`, `test_chat_aggregator.py`, `test_chat_request_images.py`, `test_provider_native_replay_state.py`. Project gates (ruff, biome, nesting, file-lines, no-tools-in-providers) all pass.

## Follow-ups

- Plumb `workspace_root` through the remaining `resolve_llm` callers that have a user/workspace in scope (telegram bot, event-bus handlers, LCM). They'll get correctly-scoped transcripts; isolation is already covered by `setting_sources=[]`.
- Repo-wide mypy is dirty in unrelated files (telegram bot, artifact_agent exports, StreamEvent TypedDict). Out of scope; worth a separate sweep.
