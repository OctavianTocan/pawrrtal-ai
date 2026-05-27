---
# pawrrtal-t5j8
title: Investigate Codex-related errors appearing in OTHER providers' chat turns
status: completed
type: bug
priority: high
created_at: 2026-05-27T13:24:14Z
updated_at: 2026-05-27T16:25:55Z
parent: pawrrtal-ujo8
---

User report on 2026-05-27: even when messaging non-Codex providers (Claude/Gemini/xAI/LiteLLM), Codex-related issues surface during chat turns. The OpenAICodexProvider should be isolated to its own Host route, so any leak suggests:

Suspects to investigate:
- backend/app/core/providers/openai_codex/__init__.py runs ensure_openai_codex_available() at import time, which inserts the vendored SDK path into sys.path and imports openai_codex. If any *other* provider's import chain transitively touches the openai_codex package, the cold-import failure (FileNotFoundError on codex binary, or AttributeError on ReasoningSummary.auto) could bubble into non-Codex turns.
- backend/app/core/providers/factory.py:30 does 'from .openai_codex import OpenAICodexProvider' at top level — so any factory import (which happens for every chat turn) imports the openai_codex package and runs the vendor bootstrap. Failure modes there could surface as errors during turns for any provider.
- backend/app/channels/turn_runner.py loads/persists codex_thread_id for every conversation (turn_runner.py:121,371,386). Even for non-Codex turns, the codex_thread_id may be read. Worth checking for null-handling bugs.
- backend/app/plugins/openai_codex_image_gen/ — if registered as a tool plugin for the agent loop, it may be offered as a tool to non-Codex agents and fail.

## Todos
- [ ] Reproduce: send a message via Claude / Gemini / xAI / LiteLLM and capture exact error
- [ ] Check whether factory.py's top-level openai_codex import raises at module load when binary is missing
- [ ] Audit turn_runner.py paths that touch codex_thread_id for non-Codex conversations
- [ ] Check whether openai_codex_image_gen plugin is registered for non-Codex hosts
- [ ] Determine if image-gen path (image_gen.py) is shared with the new provider's auth and fails for image generation across providers
- [ ] Fix root cause, add regression test

## Summary of Changes (2026-05-27)

Root cause: backend/app/core/providers/openai_codex/__init__.py ran ensure_openai_codex_available() at module import time, and backend/app/core/providers/factory.py:30 imported OpenAICodexProvider at the top level. Every chat turn (regardless of provider) paid the Codex SDK bootstrap cost, so any failure (missing codex binary, ReasoningSummary AttributeError) surfaced inside an unrelated turn.

Fixed in Task 0 of plan docs/superpowers/plans/2026-05-27-codex-provider-fix.md:
- Lazy module-level __getattr__ in openai_codex/__init__.py (commit 1f854fd4)
- factory.py resolves OpenAICodexProvider via _load_openai_codex_provider_cls inside resolve_llm (commit 1f854fd4)
- inputs.py bootstraps the vendored SDK only when its own module is loaded (commit 94c834ff)
- Regression test in backend/tests/test_openai_codex_import_isolation.py (commit 36c0b5d6 — meta_path blocker survives module reload)
