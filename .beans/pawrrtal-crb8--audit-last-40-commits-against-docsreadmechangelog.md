---
# pawrrtal-crb8
title: Audit last 40 commits against docs/README/CHANGELOG
status: completed
type: task
priority: normal
created_at: 2026-05-18T18:49:32Z
updated_at: 2026-05-18T19:12:14Z
---

Cross-check recent commit history against project docs to identify documentation drift

## Summary of Changes

Audited last 40 commits against README.md, CHANGELOG.md, AGENTS.md/CLAUDE.md, DESIGN.md, and frontend/content/docs/handbook/. Used Explore subagent for read-only investigation.

**Finding**: significant drift in the last ~18 hours. 9 feature commits landed after the most recent README refresh (7bfdb9a2, May 18 14:57 UTC) with no CHANGELOG entries and no README updates.

**Gaps**:
- CHANGELOG missing: #327 OpenCode Go (GLM-5.1, Kimi K2.6), #323 LiteLLM provider, #324 xAI SDK swap, #314 xAI provider, #333 Heartbeat/JobScheduler bridge, #265 interactive artifact widgets, #329 dev-admin workspace pinning, #320 cron follow-up
- README missing: new providers in catalog list, OPENAI_API_KEY/XAI_API_KEY in gating section, interactive widget shapes in Artifacts, HEARTBEAT.md in Workspaces
- ADRs missing for: OpenCode Go integration, LiteLLM routing, xAI SDK swap, interactive widgets protocol, Heartbeat bridge

**Pattern**: docs are updated in retroactive batches (186593d8 was 28-file refresh; 7bfdb9a2 followed) rather than commit-by-commit. Tooling exists, discipline gap.

**Recommended**: P1 sync CHANGELOG for 9 PRs (~1h), P2 sync README for providers/widgets (~30m), P3 add commit-time CHANGELOG gate, P4 write 5 ADRs, P5 expand handbook integration docs.

## Follow-up: P1 + P2 completed

Two parallel subagents wrote the updates.

**CHANGELOG.md** — 8 new entries:
- Added: #327 OpenCode Go, #323 LiteLLM (OpenAI-only after #324 split), #314 xAI Grok 4.3, #333 Heartbeat bridge, #265 Interactive widgets, #329 Dev-admin pinning, #320 Cron tools
- Changed: #324 xAI SDK swap (openai-compat → official xai-sdk gRPC)

**README.md** — 7 sections updated (lines 25, 37-38, 56, 88-91, 214, 302-310, 565):
- Catalog: GLM-5.1, Kimi K2.6, GPT-4o/o-series, Grok 4.3
- Gating/env: OPENCODE_API_KEY, OPENAI_API_KEY, XAI_API_KEY
- Artifacts: ActionButton / ChoiceGroup / TextField / NumberField
- Workspaces: HEARTBEAT.md + POST /api/v1/heartbeat/sync route
- Tech stack providers row updated

Ambiguities resolved by diff inspection:
- LiteLLM #323 originally bundled xAI but #324 split it; CHANGELOG captures end state (OpenAI-only via LiteLLM, xAI standalone)
- HEARTBEAT.md is user-authored cron-spec parsed into scheduled_jobs, not a seeded context file alongside SOUL/AGENTS — README documented accurately under Workspaces
- #329 dev-admin pinning was skipped from README (purely dev-loop convenience, no user-facing config)

Not committed — left staged for user review.

## Follow-up: P4 + P5 completed

Five parallel subagents wrote ADRs + integration/feature docs.

**ADRs created** (frontend/content/docs/handbook/decisions/):
- 2026-05-18-opencode-go-routing.mdx
- 2026-05-18-litellm-routing.mdx
- 2026-05-18-xai-grok-sdk-swap.mdx (covers #314 + #324 as a single narrative)
- 2026-05-18-heartbeat-job-scheduler-bridge.mdx
- 2026-05-18-interactive-artifact-widgets.mdx

**Integration guides** (frontend/content/docs/handbook/integrations/):
- opencode-go.mdx
- litellm.mdx
- xai-grok.mdx

**Feature docs** (frontend/content/docs/handbook/features/ — new folder):
- heartbeat.mdx
- interactive-artifacts.mdx

**Scope incident**: xAI subagent silently modified backend/app/core/providers/xai_provider.py (removed _live_search_off helper, claimed Live Search deprecation May 2026). Not requested, claim unverifiable — reverted with git checkout. Subagent prompts going forward should explicitly forbid modifying source files when only docs are requested.

**Open TODOs flagged by subagents**:
- OpenCode Go ADR: alternatives section has TODO confirming whether OpenRouter/Together were considered
- LiteLLM ADR: notes leftover XAI_API_KEY entry in _VENDOR_API_KEY_NAME post-#324 as a tradeoff
- xAI integration guide: workspace overridable keys claim needs verification
- Heartbeat ADR: importlinter grandfather + linear scan in _remove_stale_jobs flagged as 'when to revisit', no beans tracker yet
- Heartbeat docs: Settings UI for triggering sync referenced as future-tense (not yet built)

10 new files, ~unstaged. Did NOT commit per instructions.
