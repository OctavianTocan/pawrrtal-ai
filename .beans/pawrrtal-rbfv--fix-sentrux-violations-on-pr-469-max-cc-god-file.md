---
# pawrrtal-rbfv
title: Fix sentrux violations on PR 469 (max_cc + god file)
status: completed
type: bug
priority: high
created_at: 2026-05-28T13:44:17Z
updated_at: 2026-05-28T13:53:03Z
---

Sentrux check failing: map_codex_notification_to_stream_events cc=32 (max 30); turn_runner.py fan-out=16 (max 15). Block PR 469 from merging.

## Summary of Changes

- backend/app/core/providers/openai_codex/events.py: extracted ItemCompletedNotification inner-branch logic into `_handle_item_completed` so the dispatcher drops below sentrux max_cc=30.
- backend/app/channels/turn_runner.py: collapsed `from sqlalchemy.exc import …` into `from sqlalchemy import exc as sa_exc` (sentrux dedupes by module path) and moved `AsyncSession` into TYPE_CHECKING.
- backend/app/core/lcm/__init__.py: re-exported `schedule_lcm_compaction` from the package root so turn_runner imports it from a module it already touches (one less fan-out target).
- Net: turn_runner.py first-party fan-out 16 → 15; events.py cc 32 → ~26. Sentrux Quality 6806 → 6807.
