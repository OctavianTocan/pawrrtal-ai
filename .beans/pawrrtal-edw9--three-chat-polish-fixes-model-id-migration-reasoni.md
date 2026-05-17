---
# pawrrtal-edw9
title: 'Three chat polish fixes: model-id migration, reasoning label, vendor chevron'
status: completed
type: bug
priority: normal
created_at: 2026-05-15T04:51:05Z
updated_at: 2026-05-15T04:56:11Z
---

Three small but visible defects reported together. (1) GET /api/v1/conversations 500s because legacy rows have non-canonical model_id values (claude-haiku-4-5, claude-opus-4-7, gemini-3.1-flash-lite-preview); strict_conversation_read_validation=True rejects them. Needs an Alembic migration that rewrites legacy ids to host:vendor/model form. (2) react-chat-composer lib's getReasoningLabel returns the raw level string, so the UI shows 'extra-high' instead of 'Extra High'. (3) ModelSelectorPopoverView renders ChevronRightIcon on every non-active provider row; user finds the chevron redundant alongside the active-row check. Drop the chevron.

## Summary of Changes

1. backend/alembic/versions/012_canonicalise_conversation_model_ids.py — new migration that rewrites legacy bare model_ids ('claude-haiku-4-5', etc.) to canonical 'host:vendor/model' form and converts '' to NULL. Hand-rolled LEGACY_MODEL_ID_MAP so the migration stays runnable even if the catalog module changes shape later.

2. frontend/lib/react-chat-composer/src/model-selector/model-selector-data.ts — getReasoningLabel now title-cases each kebab segment so 'extra-high' renders as 'Extra High' without a per-value override map.

3. frontend/lib/react-chat-composer/src/model-selector/ModelSelectorPopoverView.tsx — non-active provider rows no longer render ChevronRightIcon; only the active row shows a CheckIcon. Removed the now-unused ChevronRightIcon import. Submenu still opens on hover/ArrowRight.

Dev DB at repo root (pawrrtal.db) was migrated successfully: 5 conversations now have NULL model_id, the rest are canonical. backend/pawrrtal.db was created accidentally during alembic stamping (relative ./pawrrtal.db) and should be deleted by the operator — the auto-mode classifier blocked me from removing it.

Verification: bun run check passes (Biome + tsc + file-lines + nesting + view-container all clean apart from the same pre-existing MONOLITH advisories).

Follow-up not done here: no unit test added for getReasoningLabel because the react-chat-composer submodule has no test infrastructure wired up yet (no src/__tests__ dir, no vitest config in the lib). Filing as a deferred follow-up would be welcome.
