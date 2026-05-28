---
# pawrrtal-ca8v
title: 'pilot(crud): Maybe[Row] migration for crud/conversation + crud/message'
status: todo
type: task
priority: deferred
created_at: 2026-05-28T09:53:48Z
updated_at: 2026-05-28T09:54:25Z
blocked_by:
    - pawrrtal-3lnz
---

From returns adoption grilling spec, Phase 2. After Phase 1 net-positive: migrate crud/conversation.get_conversation and crud/message.get_message_by_id to return Maybe[Row]. Two call sites. Watch the diff land in code review. Decision rule for Phase 3: clear wins exceptions wouldn't have caught. Cost: ~1 week.
