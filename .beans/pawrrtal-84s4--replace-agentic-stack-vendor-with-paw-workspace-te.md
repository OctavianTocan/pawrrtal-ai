---
# pawrrtal-84s4
title: Replace agentic-stack vendor with Paw workspace template
status: completed
type: task
priority: normal
created_at: 2026-05-21T19:25:39Z
updated_at: 2026-05-21T19:36:58Z
---

Reshape PR #423 so Pawrrtal owns the workspace template directly. Remove vendor/agentic-stack and all manager/adapters/overlay/backwards-compatible residue. Seed root-level .env, AGENTS.md, HEARTBEAT.md, SOUL.md, PREFERENCES.md, USER.md; create CLAUDE.md -> AGENTS.md, .agents/skills -> ../.agent/skills, and .claude/skills -> ../.agent/skills; keep .agent only for internal memory/protocols/harness/tools/skills. Update backend readers and tests to use the new contract only. Required cleanup scan: no active backend/test/template refs to vendor/agentic-stack, agentic_stack, paw-overlay, .agent/AGENTS.md, .agent/HEARTBEAT.md, .agent/memory/personal/PREFERENCES.md, .pawrrtal, BOOTSTRAP.md, IDENTITY.md, or TOOLS.md.

## Implementation Checklist\n\n- [x] Remove vendor/agentic-stack submodule and all agentic_stack / paw-overlay seeding logic.\n- [x] Add a single Pawrrtal-owned backend/templates/workspace template.\n- [x] Seed root .env, AGENTS.md, HEARTBEAT.md, SOUL.md, PREFERENCES.md, USER.md.\n- [x] Keep .agent only for memory/protocols/harness/tools/skills internals.\n- [x] Create compatibility symlinks: CLAUDE.md -> AGENTS.md, .agents/skills -> ../.agent/skills, .claude/skills -> ../.agent/skills.\n- [x] Update backend readers to use the new root-level contract only.\n- [x] Rewrite tests to assert the new shape and remove legacy compatibility expectations.\n- [x] Run residue scan for forbidden active refs: vendor/agentic-stack, agentic_stack, paw-overlay, .agent/AGENTS.md, .agent/HEARTBEAT.md, .agent/memory/personal/PREFERENCES.md, .pawrrtal, BOOTSTRAP.md, IDENTITY.md, TOOLS.md.\n- [x] Run focused backend tests and lint/type gates.

## Summary of Changes

Replaced the old vendor-backed workspace seed with a Pawrrtal-owned backend/templates/workspace template, moved AGENTS/HEARTBEAT/PREFERENCES readers to root files, kept skills in .agent/skills, removed the agentic-stack gitlink and paw-overlay template, updated tests/docs, ran focused pytest, and completed residue scans.
