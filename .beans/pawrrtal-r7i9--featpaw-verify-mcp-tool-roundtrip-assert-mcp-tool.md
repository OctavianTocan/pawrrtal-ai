---
# pawrrtal-r7i9
title: 'feat(paw): verify mcp-tool-roundtrip — assert MCP tool invocation flows through chat'
status: todo
type: feature
priority: normal
created_at: 2026-05-28T09:14:50Z
updated_at: 2026-05-28T09:14:50Z
---

From paw v3 brainstorm Thread 4. Register an MCP server, send a chat turn that should invoke it, assert tool_call + tool_result events flow through SSE. Today paw mcp covers CRUD only — no scenario asserts MCP tools actually get called during a chat turn.
