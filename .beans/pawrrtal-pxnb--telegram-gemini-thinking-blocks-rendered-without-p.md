---
# pawrrtal-pxnb
title: 'Telegram: Gemini thinking blocks rendered without paragraph separation'
status: todo
type: bug
priority: normal
created_at: 2026-05-19T12:36:03Z
updated_at: 2026-05-19T12:37:57Z
---

Gemini provider's _split_chunk_text joins multiple thinking Parts with no separator; Telegram dispatch then joins consecutive chunks with single \n. Distinct Gemini thinking blocks render with no visual separation. Fix together with the xAI per-word bug: drop \n-join in dispatch and emit '\n\n' between thinking Parts in the Gemini provider.



## Tracking

- GitHub: https://github.com/OctavianTocan/Pawrrtal-AI/issues/351

## Related

- Pairs with `pawrrtal-o0wq` (#345 — xAI per-word). Same dispatch site; fix together.
