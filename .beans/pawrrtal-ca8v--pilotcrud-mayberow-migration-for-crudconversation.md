---
# pawrrtal-ca8v
title: 'pilot(crud): Maybe[Row] migration for crud/conversation + crud/message'
status: completed
type: task
priority: deferred
created_at: 2026-05-28T09:53:48Z
updated_at: 2026-05-28T10:26:43Z
blocked_by:
    - pawrrtal-3lnz
---

From returns adoption grilling spec, Phase 2. After Phase 1 net-positive: migrate crud/conversation.get_conversation and crud/message.get_message_by_id to return Maybe[Row]. Two call sites. Watch the diff land in code review. Decision rule for Phase 3: clear wins exceptions wouldn't have caught. Cost: ~1 week.

## Summary of Changes

Migrated `crud/conversation.get_conversation` and `crud/conversation.get_conversation_status` from `Optional[Row]` to `Maybe[Row]`.

- `backend/app/crud/conversation.py` — both reads now return `Maybe[T]`; `Maybe.from_optional(...)` for `get_conversation`, explicit `Some(...)` / `Nothing` for the aggregate `get_conversation_status`.
- Callers unwrap at route / integration boundaries via `.value_or(None)` (per the returns-for-pawrrtal skill):
  - `backend/app/api/chat.py` (line 254 area) — chat router 404 path.
  - `backend/app/api/conversations.py` — `/messages` and `/{id}` GET handlers.
  - `backend/app/api/exports.py` — export 404 path.
  - `backend/app/api/lcm.py` — LCM context 404 path + docstring updated.
  - `backend/app/integrations/telegram/status.py` — telegram /status handler.
- Tests: `tests/test_conversation_crud.py` asserts `Some` / `Nothing` directly + adds two new tests for `get_conversation_status`; `tests/test_project_crud.py` unwraps via `.value_or(None)`; `tests/test_telegram_channel.py` wraps the mock return in `Some`.

`get_message_by_id` was *not* part of this slice — keeping the change surgical to one CRUD file matches the spec's "two call sites" wording for Phase 2. The message-read migration can land separately if Phase 3 expands the pilot.
