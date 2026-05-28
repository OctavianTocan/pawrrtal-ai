---
# pawrrtal-m2pg
title: 'feat(paw): paw mcp — MCP server CRUD'
status: in-progress
type: feature
priority: low
created_at: 2026-05-27T20:08:17Z
updated_at: 2026-05-28T00:15:42Z
parent: pawrrtal-6cnv
---

v2 paw command. MCP server list/show/create/update/delete. Parent: pawrrtal-6cnv.

## Summary of Changes

Shipped `paw mcp` subcommand group targeting `/api/v1/mcp/servers`:

- `paw mcp list` / `ls` — GET, human/json/plain.
- `paw mcp show <id>` — resolves client-side from the list (backend has no per-row GET).
- `paw mcp create --name --config <json> --status` — POST.
- `paw mcp update <id>` — fills missing fields from current row, PATCHes full body.
- `paw mcp delete <id> --yes` — DELETE, idempotent on 404.

Skipped `paw mcp test`: backend exposes no per-row ping/health endpoint (external-MCP bridge is invoked only during a chat turn).

Backend mount path discovery: bean spec referenced `/api/v1/mcp-servers`; the real router is mounted at `/api/v1/mcp/servers` (`backend/app/api/mcp_servers.py:60`). CRUD body shape uses `name` + `config: dict` + `status: 'enabled'|'disabled'` (no `url`/`transport` — those go inside opaque `config`).

Tests: `backend/tests/paw/test_command_mcp.py` (17 tests, respx-mocked). Full paw suite: 133 passed (116 + 17).

Files: `backend/app/cli/paw/commands/mcp.py`, `backend/app/cli/paw/main.py`, `backend/tests/paw/test_command_mcp.py`, `.claude/skills/paw/SKILL.md` (added `mcp` row to Resource map, removed from Deferred-to-v2).
