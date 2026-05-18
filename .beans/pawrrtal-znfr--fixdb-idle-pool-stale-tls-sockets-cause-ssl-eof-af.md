---
# pawrrtal-znfr
title: 'fix(db): idle-pool stale TLS sockets cause SSL EOF after long idle (Railway)'
status: in-progress
type: bug
priority: high
created_at: 2026-05-18T06:51:24Z
updated_at: 2026-05-18T06:52:09Z
---

Telegram bot first DB query failed with `psycopg.OperationalError: consuming input failed: SSL SYSCALL error: EOF detected` after 8h idle on Railway deploy 2026-05-17. Root cause: SQLAlchemy async engine in `backend/app/db.py` has no `pool_pre_ping`, no `pool_recycle`, no TCP keepalives; Railway proxy / managed Postgres silently evicts the idle TCP, pool hands the dead socket to first checkout after idle window.

Fix (Claude + Codex consult agree):
- [x] backend/app/db.py: add pool_pre_ping=True, pool_recycle=1800, pool_timeout=10
- [x] backend/app/db.py: add connect_args with connect_timeout=10 + libpq keepalives (idle=30, interval=10, count=5)
- [ ] Verify Railway DATABASE_URL uses internal *.railway.internal host, not public TCP proxy
- [ ] Deploy + smoke test (wait 8h+ idle and send Telegram message, should not EOF)

Codex session: 019e39d2-aef6-7db1-bf64-ba913b57880b
