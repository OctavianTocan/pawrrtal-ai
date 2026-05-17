---
# pawrrtal-jmhz
title: 'Fix keys.py: path, InvalidToken, newline injection, perf, semantics'
status: completed
type: bug
priority: critical
created_at: 2026-05-09T06:52:11Z
updated_at: 2026-05-09T06:59:01Z
parent: pawrrtal-c6tc
---

Address all keys.py findings. Todos: replace WORKSPACE_BASE hardcode with settings.workspace_base_dir; move keys.py from core/providers/ to core/ and update imports; wrap decrypt in try/except InvalidToken with corrupt-file rename + WARN log; reject newline chars in PUT validator; cache Fernet at module scope; wrap sync file I/O in asyncio.to_thread; bound or remove module-level _env_cache; add asyncio.Lock if cache stays; switch mtime to st_mtime_ns; remove dead workspace_encryption_key falsy guard; strip empty values before save so clear-and-save reverts to gateway default; add docstrings to all public functions.



## Summary of Changes

- **Moved** keys.py from `backend/app/core/providers/keys.py` → `backend/app/core/keys.py` (cross-cutting helper, not a provider). Updated 8 import sites: agents.py, claude_provider.py, agent_tools.py, exa_search_agent.py, exa_search_agno.py, gemini_provider.py, workspace_env.py, stt.py.
- **Replaced** hardcoded `Path('/workspace')` with `Path(settings.workspace_base_dir)` so workspace files land on the persisted Docker volume and macOS dev no longer hits PermissionError.
- **Added** InvalidToken catch in load_workspace_env: corrupt/key-rotated files are quarantined to a sibling .env.corrupt-{ts} path with a WARNING log; user gets an empty dict and can re-enter keys instead of being permanently locked out.
- **Added** newline rejection at the Pydantic validator level (WorkspaceEnvVars._reject_newlines + VALUE_FORBIDDEN_CHARS regex). A value with \n can no longer split into multiple key=value lines and overwrite other entries.
- **Cached** Fernet at module scope via @lru_cache(maxsize=1) — was being rebuilt on every call.
- **Removed** the module-level _env_cache entirely. The decryption cost per call is trivial; bounded LRU + asyncio.Lock + st_mtime_ns + multi-worker invalidation were all complexity in service of a perf gain that isn't measurable. Per-request reads also fix the multi-worker stale-read bug.
- **Removed** the dead `if not settings.workspace_encryption_key` guard.
- **Strip** empty-string values during save_workspace_env serialization so clear-and-save in the UI reverts the key to the gateway default (matches resolve_api_key's falsy-empty fallback).
- **Added** docstrings to all public functions and the module.
- **Removed** redundant `or settings.x` double-fallback in stt.py:60 (resolve_api_key already falls back via _SETTINGS_ATTR_MAP).
- **Simplified** agent_tools.py + agents.py Exa key gating to a single resolve_api_key call.
- **Made** GeminiLLM.user_id Optional (was required) to match ClaudeLLM and avoid a TypeError when the factory is called without a user.
- **Fixed** pre-existing E402 in claude_provider.py with an explicit noqa explaining the deliberate post-class re-export.

Smoke-tested: round-trip save/load works, empty-string strip works, workspace override beats settings, corrupt-file quarantine works, ruff clean across all touched files.
