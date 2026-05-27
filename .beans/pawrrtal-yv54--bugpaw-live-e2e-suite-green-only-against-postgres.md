---
# pawrrtal-yv54
title: 'bug(paw): live E2E suite green only against Postgres — SQLite chat path failing'
status: todo
type: bug
priority: normal
created_at: 2026-05-27T20:08:18Z
updated_at: 2026-05-27T20:08:18Z
---

When PAW_E2E=1 runs against a SQLite backend the chat-roundtrip path fails. Postgres is green. Need to diagnose whether the chat router or persistence assumes Postgres semantics (JSONB? array contains?). Parent: pawrrtal-6cnv.
