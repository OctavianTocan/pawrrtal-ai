---
# pawrrtal-m20f
title: 'ci(paw): wire PAW_E2E=1 live gate into GitHub Actions'
status: completed
type: task
priority: normal
created_at: 2026-05-27T20:08:18Z
updated_at: 2026-05-28T00:00:19Z
---

Wire the backend/tests/e2e_paw/ suite (PAW_E2E=1) into the CI workflow. Today these tests are gated and only run locally. Need a job that boots a real backend + Postgres and runs the 2 live tests. Parent epic: pawrrtal-6cnv (paw v1).
