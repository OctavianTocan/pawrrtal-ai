---
# pawrrtal-1gbp
title: 'Schema: add block-boundary metadata to thinking StreamEvent'
status: todo
type: feature
priority: high
created_at: 2026-05-19T12:55:55Z
updated_at: 2026-05-19T12:58:40Z
---

Unified StreamEvent type='thinking' carries only {content:str} so the channel dispatcher cannot distinguish xAI per-token fragments from Gemini per-block emission. Add block_index or explicit thinking_block_start/end so renderers can apply correct separators without policy-guessing. Blocks pawrrtal-o0wq and pawrrtal-pxnb.



## Tracking

- GitHub: https://github.com/OctavianTocan/Pawrrtal-AI/issues/353
