---
# pawrrtal-roi0
title: Wire AgentTool bridge for OpenAICodexProvider (tools currently dropped)
status: todo
type: feature
priority: normal
created_at: 2026-05-27T13:24:25Z
updated_at: 2026-05-27T13:24:54Z
blocked_by:
    - pawrrtal-pu63
---

Deferred from pawrrtal-pu63 / pawrrtal-ujo8.

Today: backend/app/core/providers/openai_codex/provider.py:129-134 logs and DISCARDS the tools= parameter ('text-only path for v1'). The whole agentic point of the SDK path (shell tool, file edits, sandbox, approvals, MCP) is inert. Codex SDK's thread_start defaults approval_mode=ApprovalMode.auto_review (vendor/codex/sdk/python/src/openai_codex/api.py:365), which means the spawned app-server binary may request escalation that the SDK then denies — currently safe by accident.

Goal: translate Pawrrtal AgentTool (backend/app/core/agent_loop/types.py) into the Codex SDK's tool-call surface so chat-router-composed tools (web search, notion, workspace files) are available inside Codex threads. Follow the pattern from backend/app/core/providers/_claude_tool_bridge.py.

## Todos
- [ ] Inspect SDK's tool-call surface (vendor/codex/sdk/python/src/openai_codex/types.py + generated.v2_all tool types)
- [ ] Decide: in-process MCP server (Claude pattern) or direct tool registration
- [ ] Implement _openai_codex_tool_bridge.py inside the openai_codex package
- [ ] Hook bridge into provider.stream() — replace the 'log and discard' block
- [ ] Pass an explicit approval_mode and approval_handler appropriate for Pawrrtal
- [ ] Tests: ScriptedStreamFn equivalent for Codex, exercising tool dispatch
- [ ] Update docs/design/codex-oauth-text-provider.md with the bridge design
