---
# pawrrtal-0dgj
title: 'bug(backend): SQLite+aiosqlite chat path raises ''no active connection'' under live E2E'
status: todo
type: bug
priority: normal
created_at: 2026-05-27T20:02:35Z
updated_at: 2026-05-27T20:02:35Z
---

Live E2E fixture from Task 9 hits 'no active connection' from SQLAlchemy/aiosqlite when paw verify chat-roundtrip drives a real chat through the booted backend.

Symptoms:
- Backend boots fine on sqlite file-backed DB
- /api/v1/health responds 200
- paw login --dev-admin succeeds (cookie + workspace bootstrap OK)
- POST /api/v1/chat/ fails server-side with sqlalchemy 'no active connection'

Production uses Postgres so the SQLite chat code path is untested. Likely the chat handler opens a connection in the request context and closes it before a background task tries to use it, OR uses StaticPool incompatibly, OR holds a transaction across an await boundary that aiosqlite can't span.

Fix path:
- Reproduce locally: PAW_E2E=1 uv run pytest backend/tests/e2e_paw/test_chat_roundtrip_live.py -x -v --tb=long
- Identify which await drops the connection
- Fix the lifecycle, OR document a Postgres-only test fixture as the canonical path
