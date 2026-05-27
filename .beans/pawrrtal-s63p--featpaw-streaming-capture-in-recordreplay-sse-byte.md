---
# pawrrtal-s63p
title: 'feat(paw): streaming capture in record/replay (SSE bytes)'
status: todo
type: feature
priority: low
created_at: 2026-05-27T20:08:18Z
updated_at: 2026-05-27T20:08:18Z
---

paw record/replay captures HTTP requests + responses but not the raw SSE byte stream. Add a dedicated writer that captures provider-emitted delta/done events frame-by-frame so replay can drive offline tests bit-for-bit. Parent: pawrrtal-6cnv.
