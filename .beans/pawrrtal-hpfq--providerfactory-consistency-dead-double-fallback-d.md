---
# pawrrtal-hpfq
title: Provider/factory consistency + dead double-fallback dedup
status: completed
type: bug
priority: high
created_at: 2026-05-09T06:52:29Z
updated_at: 2026-05-09T06:59:08Z
parent: pawrrtal-c6tc
---

Type contract + dead code cleanup across providers and tools. Todos: change GeminiLLM init user_id to optional uuid.UUID None default to match ClaudeLLM; make_gemini_stream_fn accepts None and skips workspace lookup; backend/app/api/stt.py:60 remove redundant or settings.xai_api_key suffix because resolve_api_key already falls back via _SETTINGS_ATTR_MAP; backend/app/core/agent_tools.py:80-85 remove the redundant exa_key None fallback; backend/app/core/agents.py:44-45 simplify Exa gating to a single resolve_api_key call; add a comment in keys.py resolve_api_key documenting the always-falls-back-to-settings contract so future callers do not double-fall-back.



## Summary of Changes

Folded into Bean A (pawrrtal-jmhz) since it touched the same call sites:

- backend/app/core/providers/gemini_provider.py: GeminiLLM and make_gemini_stream_fn now accept `user_id: uuid.UUID | None = None` (matches ClaudeLLM).
- backend/app/api/stt.py:60 — removed redundant `or settings.xai_api_key` suffix.
- backend/app/core/agent_tools.py:80-86 — simplified to single resolve_api_key call when user_id supplied; settings fallback only when user_id is None (background work).
- backend/app/core/agents.py:44-47 — replaced multi-line dead-branch logic with `if resolve_api_key(user_id, 'EXA_API_KEY')`.
- Added a contract comment in keys.resolve_api_key documenting that callers must NOT double-fall-back.

admin_seed.py:29 (still passes invite_code) is moved to Bean C (env/config cleanup) which handles the registration_secret deprecation in the same commit.
