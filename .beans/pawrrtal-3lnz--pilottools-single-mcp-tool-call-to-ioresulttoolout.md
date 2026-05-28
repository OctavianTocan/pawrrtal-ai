---
# pawrrtal-3lnz
title: 'pilot(tools): single MCP tool call to IOResult[ToolOutput, McpError]'
status: completed
type: task
priority: deferred
created_at: 2026-05-28T09:54:10Z
updated_at: 2026-05-28T10:32:06Z
blocked_by:
    - pawrrtal-67rg
---

From returns adoption grilling spec, Phase 1. After Phase 0 (pawrrtal-67rg) signals positive: migrate backend/app/core/tools/external_mcp.py outermost call to return IOResult. Keep call site exception-bridged so callers stay compatible. Re-do reading-glasses on the migrated code for 1 week. Cost: 3 days. Decision rule for Phase 2: shipped without bugs + review velocity didn't drop + at least one team member says 'I want this more places.'

## Summary of Changes

Shipped on `backend/app/core/tools/external_mcp.py` (+ tests). The agent-loop caller seam is unchanged: tools still resolve as `str` for the `AgentTool.execute` contract.

- New typed failure model `McpError = McpTimeoutError | McpAuthError | McpServerError | McpProtocolError` (frozen `@dataclass(slots=True)` with `kind: Literal[...]` discriminators).
- New public outermost-call function `call_external_mcp_tool(...) -> IOResult[str, McpError]` that narrows the previous broad `except (TimeoutError, json.JSONDecodeError)` catch into typed failures and preserves every existing log line.
- Closure inside `_wrap_remote_tool` delegates to the new function and unwraps via a one-call `_unwrap_mcp_result(...)` helper back to the legacy `[io_error] ...` `ToolError.render()` string the agent loop already consumes. Caller-unwrap delta: ~3 lines per call site.
- 8 new tests in `backend/tests/test_external_mcp_tools.py` covering the four failure variants and a caller-level test that asserts the legacy `[io_error]` string contract still surfaces from `tool.execute(...)`. Suite now totals 18 tests, all passing.

mypy on the touched file is clean; ruff format + check are clean.
