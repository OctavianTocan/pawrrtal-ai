---
# pawrrtal-3lnz
title: 'pilot(tools): single MCP tool call to IOResult[ToolOutput, McpError]'
status: todo
type: task
priority: deferred
created_at: 2026-05-28T09:54:10Z
updated_at: 2026-05-28T09:54:25Z
blocked_by:
    - pawrrtal-67rg
---

From returns adoption grilling spec, Phase 1. After Phase 0 (pawrrtal-67rg) signals positive: migrate backend/app/core/tools/external_mcp.py outermost call to return IOResult. Keep call site exception-bridged so callers stay compatible. Re-do reading-glasses on the migrated code for 1 week. Cost: 3 days. Decision rule for Phase 2: shipped without bugs + review velocity didn't drop + at least one team member says 'I want this more places.'
