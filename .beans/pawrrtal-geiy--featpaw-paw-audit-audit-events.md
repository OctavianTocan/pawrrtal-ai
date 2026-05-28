---
# pawrrtal-geiy
title: 'feat(paw): paw audit — audit events'
status: completed
type: feature
priority: low
created_at: 2026-05-27T20:08:17Z
updated_at: 2026-05-28T00:32:16Z
parent: pawrrtal-6cnv
---

v2 paw command. Audit event browsing. Parent: pawrrtal-6cnv.

## Summary of Changes

Shipped `paw audit ls / list / show` — read-only inspection of the
per-user audit log over `GET /api/v1/audit/`.

### Verbs

- `paw audit ls` — paginated list (newest-first). Flags: `--limit`
  (1..1000), `--offset` (>= 0), `--event-type` (exact match),
  `--since` (ISO-8601 timestamp), `--profile`, `--json`, `--plain`.
  `paw audit list` registered as an alias.
- `paw audit show <id>` — single event. The backend exposes no
  per-row GET endpoint, so this resolves the row client-side by
  scanning the list response (same pattern as `paw mcp show`).

### Skipped flags (with reason)

`--until`, `--actor`, `--resource-type`, `--resource-id`. The
backend list endpoint in `backend/app/api/audit.py` does not accept
any of those today; exposing them would silently no-op. Use
`paw audit ls --plain` piped through `awk` / `grep` for one-off
slicing on those axes.

### Files

- `backend/app/cli/paw/commands/audit.py` — new Typer app.
- `backend/app/cli/paw/main.py` — `add_typer` registration.
- `backend/tests/paw/test_command_audit.py` — 18 respx tests
  covering list (filters, pagination, output modes, exit codes),
  show (found, not found, 401), and edge cases.
- `.claude/skills/paw/SKILL.md` — added `audit` row to the Resource
  map and removed it from "Deferred to v2".

### Verification

- `uv run pytest -q tests/paw/test_command_audit.py` — 18 passed.
- `uv run pytest -q tests/paw -x` — 171 passed (was 153; +18).
- `uv run ruff check app/cli/paw/commands/audit.py
  app/cli/paw/main.py tests/paw/test_command_audit.py` — clean.
- `uv run mypy app/cli/paw/commands/audit.py app/cli/paw/main.py`
  — clean.
- `uv run paw audit --help` — typer help renders.
