---
# pawrrtal-s0w4
title: 'Telegram legacy text path: only first chunk shows when text follows thinking/tools'
status: todo
type: bug
priority: critical
created_at: 2026-05-19T12:35:48Z
updated_at: 2026-05-19T12:37:47Z
---

When telegram_use_draft_streaming=False and a thinking or tool block precedes assistant text, dispatch_text_delta short-circuits on previous_block_kind='text' and finalize_turn_delivery edits the interleaved message with only the first chunk before returning — full answer_text is never sent.



## Tracking

- GitHub: https://github.com/OctavianTocan/Pawrrtal-AI/issues/346

## Evidence

- Bug site (short-circuit): `backend/app/channels/_telegram_dispatch.py:374-376`
- Bug site (truncated flush): `backend/app/channels/_telegram_dispatch.py:496-498`
- Caller setting `previous_block_kind = 'text'`: `backend/app/channels/telegram.py:305-311`
- Related (already-fixed draft variant): commit `19f198dc fix(telegram): rendering regressions from visual overhaul`
