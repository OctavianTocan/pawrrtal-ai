---
# pawrrtal-khmh
title: Fix stale workspace_id kwarg in telegram bot_provider_resolution
status: completed
type: bug
priority: high
created_at: 2026-05-19T11:48:54Z
updated_at: 2026-05-19T11:51:32Z
---

resolve_llm signature lost the workspace_id parameter in commit f6f70eaa, but two call sites in backend/app/integrations/telegram/bot_provider_resolution.py still pass it. TypeError fires on every Telegram message. Drop the workspace_id= kwarg from both call sites (and the dead parameter on the wrapper).

## Summary of Changes

Dropped the dead workspace_id parameter from:
1. resolve_provider_with_auto_clear() function signature
2. Both resolve_llm call sites in bot_provider_resolution.py
3. Two test call sites in test_telegram_channel.py
4. Removed stale 'import uuid' (only used for the deleted parameter type)

Fixed in commit d67e66f2.
