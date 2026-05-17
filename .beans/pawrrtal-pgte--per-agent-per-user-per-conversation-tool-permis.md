---
# pawrrtal-pgte
title: 'Per-agent / per-user / per-conversation tool-permission gating'
status: todo
type: task
priority: medium
created_at: 2026-05-08T20:10:00Z
updated_at: 2026-05-08T20:10:00Z
---

## Description

Right now `app.core.agent_tools.build_agent_tools` returns the same
tool list for every chat turn — workspace tools always, Exa when the
key is configured.  No notion of "this agent / this user / this
conversation gets a different subset."

The architecture is set up for it (PR #131 made tool composition
provider-agnostic and the chat router owns it), but the gating layer
itself doesn't exist yet.  This bean tracks landing it.

## Why this is a follow-up, not part of #131

PR #131 was about *where* tool composition lives (the chat router,
not the providers).  Adding gating now would conflate two changes
and balloon the diff.  The seam exists; this bean fills it.

## Shape of the work

Probably wants three layers, applied in order, all inside
`build_agent_tools`:

1. **Per-agent allowlist.**  An agent's identity (set per-conversation
   today via `agentId` / channel routing) maps to a set of allowed
   tool names.  Default: all tools allowed.  Wretch-style \"trusted
   builder\" gets the full set; a user-facing assistant might get
   read-only workspace tools + web search and nothing else.

2. **Per-user override.**  The user's settings can further restrict
   their own agent's tools (\"never let this agent edit my files\").
   Stored in the user row; merged with the agent allowlist by
   intersection.

3. **Per-conversation override.**  A user can opt one specific
   conversation into a tighter or looser tool set without changing
   the global default.  Stored on the conversation row.

Composition: `agent_allowed ∩ user_allowed ∩ conversation_allowed`.

## Acceptance criteria

- [ ] `build_agent_tools` accepts `agent_id`, `user_id`, `conversation_id`
- [ ] Agent → tool-allowlist mapping lives in a config file or DB
      table (start with config; migrate later)
- [ ] User-level + conversation-level overrides land in DB
- [ ] Unit tests for the intersection algebra (each layer included,
      identity, empty intersection, etc.)
- [ ] Smoke test against the chat router that an agent without
      `read_file` actually doesn't see it in
      `provider.stream(tools=...)`

## See also

- `backend/app/core/agent_tools.py` — the seam where gating lands.
- `.claude/rules/architecture/no-tools-in-providers.md` — why this
  has to live above the providers, not inside them.
- PR #131 review thread comment 3210956416.
