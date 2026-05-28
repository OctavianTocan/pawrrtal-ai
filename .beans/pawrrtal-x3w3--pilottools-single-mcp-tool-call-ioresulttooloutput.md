---
# pawrrtal-x3w3
title: 'pilot(tools): single MCP tool call → IOResult[ToolOutput, McpError]'
status: scrapped
type: task
priority: deferred
created_at: 2026-05-28T09:53:48Z
updated_at: 2026-05-28T09:54:25Z
---

From returns adoption grilling spec, Phase 1. After Phase 0 signals positive: migrate backend/app/core/tools/external_mcp.py's outermost call to return IOResult. Keep call site exception-bridged so callers stay compatible. Re-do reading-glasses on the migrated code for 1 week. Cost: ~3 days. Decision rule for proceeding to Phase 2: shipped without bugs + review velocity didn't drop + at least one team member says 'I want this more places.'

## Reasons for Scrapping

Duplicate created when --json output didn't return id; superseded by pawrrtal-3lnz.
