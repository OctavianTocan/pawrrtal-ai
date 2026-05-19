---
# pawrrtal-22sx
title: Flatten TelegramChannel.deliver() nesting (depth=5)
status: todo
type: task
priority: normal
created_at: 2026-05-19T07:47:25Z
updated_at: 2026-05-19T07:47:25Z
parent: pawrrtal-7k7w
---

deliver() in backend/app/channels/telegram.py is depth=5, violating the 3-level Python nesting budget enforced by scripts/check-nesting.py. Initially attempted as part of pawrrtal-uecv (Task 5 of three-level model picker) by extracting _update_progress_preview, but that pushed telegram.py over the 500-line file budget. Split into its own follow-up task. Approach options: (a) move _update_progress_preview into _telegram_dispatch.py, (b) flatten the inline if/else differently. _telegram_dispatch.py is currently 524 lines (also over budget, pre-existing) so option (a) would need a separate file-shrink pass too.
