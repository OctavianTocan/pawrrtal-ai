---
# pawrrtal-uhvn
title: 'Backend restructure: hybrid domains + infrastructure, drop returns'
status: in-progress
type: epic
priority: high
created_at: 2026-05-28T15:53:29Z
updated_at: 2026-05-28T16:05:50Z
---

Full implementation of docs/superpowers/specs/2026-05-28-backend-restructure-design.md. Single big-bang PR on branch restructure/backend-domains. 16 stepped commits, CI green per commit.

## Progress as of 2026-05-28 session end

Landed on `restructure/backend-domains`:
- Spec + plan committed
- Phase 0 (CI baseline fixes): vendor pytest exclude, alembic-heads fix, e2e archived-heading scope
- Phase 1 (infrastructure/ skeleton): 12 `__init__.py` files
- Phase 2.1 (LifecycleRegistry): startup/shutdown hook registry with tests

Remaining: Phase 2.2-2.3 (startup hooks + app_factory + slim main.py) + Phases 3-16.
Plan doc has every remaining task spelled out with file paths and code blocks.
