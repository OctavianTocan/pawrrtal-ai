---
# pawrrtal-6cnv
title: 'feat(paw): Pawrrtal Agent CLI for end-to-end testing'
status: completed
type: epic
priority: high
created_at: 2026-05-27T17:08:50Z
updated_at: 2026-05-27T20:07:43Z
---

**Plan:** docs/superpowers/plans/2026-05-27-agent-cli-user.md (v2)

**Skill:** .claude/skills/paw/SKILL.md (live)

paw is a new CLI persona (Python typer, installed via uv, console script) that drives the Pawrrtal backend over the same HTTP API the React frontend uses. Replaces the weak verification pattern of importing app.* directly. v1 ships paw verify codex / chat-roundtrip / model-switch as runnable proofs.

Design influenced by:
- ntn (Notion CLI) — resource+verb structure, doctor command, three output modes, hint-bearing errors, paw api passthrough
- An adversarial review that caught three load-bearing v1 bugs (required conversation_id, missing codex_thread_id in response, models envelope) — fixed in plan v2
- A gap-hunt that mapped 26 backend subsystems to coverage; v1 covers the headline 6, v2 deferred

## v1 todos (tracked here)
- [x] Task 0: backend prerequisite — expose codex_thread_id in ConversationRead — commit `e0b3ed2f`
- [x] Task 1: package skeleton + paw doctor — commit `53c461fd`
- [x] Task 2: HTTP client w/ cookie jar + paw login/logout/auth status — commit `5cc60796`
- [x] Task 3: SSE consumer (frontend-parity) — commit `de0f8229`
- [x] Backend API gaps + mypy sweep (between Tasks 3 & 4) — commits `5ec2992b`, `a8ac063c`, `6b96f690`, `5f777f28`, `4d710e31`
- [x] Task 4: paw conversations create/send/show/ls/delete (UUID-first flow) + login test fix — commits `e81d86ba`, `c6782503`
- [x] Task 5: paw workspaces / workspace env|files / models / messages — commits `4c1437ee`, `ec2258f9`
- [x] Task 6: paw api passthrough + record/replay — commit `f986f8fa`
- [x] Task 7: paw verify codex (the proof) — commit `c872f599`
- [x] Task 8: paw verify chat-roundtrip + model-switch + all — commit `d60cd1f2`
- [x] Task 9: live E2E gate (PAW_E2E=1) — commit `a27c540c` (CI workflow filed as follow-up bean)
- [x] Task 10: .claude/skills/paw/SKILL.md polish — this commit
- [x] Task 11: docs cross-references + bean closure — this commit

## v2 (file as separate child beans when v1 lands)
- paw channels (telegram link, simulate-update)
- paw mcp ls/add/rm
- paw cost summary/ledger
- paw audit
- paw jobs
- paw lcm + memories + dreaming
- paw fanout N — parallel personas
- paw mirror --upstream — local vs remote SSE diff
- verify telegram-link-and-bot
- verify cost-and-budget
- verify lcm-active-recall
- paw dev up/down/status

## Summary of Changes (2026-05-27)

v1 of `paw` is live on `development`. ~15 commits across 12 tasks, landing 26 CLI source files + 21 test files (104 mocked tests passing, 2 live E2E tests gated on `PAW_E2E=1`).

Plan: `docs/superpowers/plans/2026-05-27-agent-cli-user.md`
Skill: `.claude/skills/paw/SKILL.md`

Headline shipped commands: `doctor`, `env`, `login/logout/auth status`, `workspaces` (full CRUD), `workspace env/files`, `models`, `conversations` (full CRUD + send + export), `messages`, `api` (passthrough + openapi + ls), `record`/`replay`, `verify codex/chat-roundtrip/model-switch/all`.

The canonical end-to-end proof for the Codex provider is now `just paw verify codex --json` (8 HTTP calls + 17 named assertions, including `codex_thread_id` persistence). The Codex design doc (`docs/design/codex-oauth-text-provider.md`) now references this as the canonical verification artefact.

**v2 deferred** (will land as separate child beans):
channels, mcp, cost, audit, jobs, lcm, fanout, mirror, verify telegram-link-and-bot, verify cost-and-budget, verify lcm-active-recall, dev up/down/status.

**Open follow-up beans:**
- CI workflow wiring (`PAW_E2E=1` gate in GitHub Actions)
- SQLite chat-path bug (live E2E currently green only against Postgres)
- Streaming capture in `record`/`replay` (HTTP capture works; SSE stream bytes need a dedicated writer)
- Frontend migration off the `/users/me` compat alias to canonical `/api/v1/users/me`
