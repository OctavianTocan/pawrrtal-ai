---
# pawrrtal-mh0x
title: Paw identity and first-run persona bootstrap
status: completed
type: feature
priority: normal
created_at: 2026-05-17T10:02:41Z
updated_at: 2026-05-17T10:09:59Z
---

Add a durable Paw conceptual identity to agent system prompts, plus a first-run persona bootstrap that asks the user who their Paw should be and stores the result for future turns.\n\nTodos:\n- [x] Identify current system prompt/workspace context assembly path\n- [x] Add default Paw identity prompt layer\n- [x] Add workspace-level bootstrap file seeding/status helpers\n- [x] Route first-run bootstrap turns into the agent context\n- [x] Add tests for prompt composition and bootstrap lifecycle\n- [x] Run focused backend verification



## Summary of Changes

- Added a shared Paw core system prompt so every provider and workspace prompt knows the agent is the user's Paw, while name/personality remain user-customizable.
- Added first-run persona bootstrap helpers that seed BOOTSTRAP.md, track completion via .pawrrtal/persona_bootstrap.json, and backfill untouched existing workspaces.
- Included pending BOOTSTRAP.md in workspace prompt assembly until completion, then omitted it.
- Updated workspace seed templates to use Paw language.
- Added focused tests for prompt composition, bootstrap seeding/completion, and workspace prompt assembly.

## Verification

- uv run ruff check on changed backend files
- pytest focused backend suite: 137 passed
- python3 scripts/check-nesting.py
- node scripts/check-file-lines.mjs
