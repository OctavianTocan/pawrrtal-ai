---
# pawrrtal-2qi1
title: 'feat(api): expose LCM lineages, memories, and dreaming as HTTP endpoints'
status: todo
type: feature
priority: normal
created_at: 2026-05-28T00:43:01Z
updated_at: 2026-05-28T00:43:01Z
---

Currently only GET /api/v1/lcm/conversations/{conv_id}/context is exposed. The rest of LCM (lineage list/get), memories (list/get/CRUD), and dreaming (manual trigger) are internals-only. Block: paw verify lcm-active-recall (pawrrtal-7uo7) can't run E2E without these. Endpoints needed: GET /api/v1/lcm/lineages, GET /api/v1/lcm/lineages/{id}, GET /api/v1/memories, GET /api/v1/memories/{id}, POST /api/v1/dreaming/trigger. Discovered during Task 10 (pawrrtal-gw5b) when the paw lcm CLI hit a wall.
