---
# pawrrtal-67rg
title: 'experiment(backend): returns reading-glasses on provider/CRUD/MCP PRs'
status: completed
type: task
priority: low
created_at: 2026-05-28T09:53:47Z
updated_at: 2026-05-28T10:45:40Z
---

## Goal

Run the Phase 0 reading-glasses experiment from the returns-adoption
grilling spec. We shipped Phases 1/2/3 on three narrow surfaces before
running the Phase 0 evidence pass, so this work applied the same rubric
**retrospectively** to the un-migrated provider / CRUD / tool code.

## Summary of changes

- Walked every un-migrated provider (claude, gemini, gemini_cli, xai,
  opencode_go, openai_codex, agy_cli), every un-migrated CRUD module
  (channel, chat_message, cost, mcp_servers, memory, project,
  workspace, audit), and every un-migrated tool factory under
  `backend/app/core/tools/`.
- Applied the four-step decision rubric from
  `.claude/skills/returns-for-pawrrtal/SKILL.md` to each significant
  error-handling site. Produced 11 strong-YES annotations and 10
  MAYBE annotations; everything else was a NO with a one-line reason.
- Captured the corpus, the synthesis, and the decision-rule outcome
  in `docs/superpowers/specs/2026-05-28-returns-phase-0-corpus.md`.

## Outcome

The Phase 0 → Phase 1 decision rule **passes** — but the clusters are
`Maybe[Row]` across CRUD (4 sites) and `Result[T, ToolError]` across
tools (4 sites), **not** the provider seam the original spec assumed.
The provider-seam pattern fails: six of seven un-migrated providers
use `except Exception` blankets that would only produce the
`Result[T, Exception]` anti-pattern the skill bans.

## Recommendation

Expand the existing `Maybe[Row]` (Phase 2) and `Result[T, ToolError]`
(Phase 1) pilots to the clustered sites; freeze the provider-seam
pilot (`pawrrtal-0zne`) unless the non-Claude providers add typed
errors later. Three follow-up beans proposed in the corpus document.

## No code changes

Phase 0 was explicitly annotation-only. No code was touched in this
work; the three pilot surfaces (`tools/external_mcp.py`,
`crud/conversation.py`, `providers/litellm_provider.py`) are out of
scope.
