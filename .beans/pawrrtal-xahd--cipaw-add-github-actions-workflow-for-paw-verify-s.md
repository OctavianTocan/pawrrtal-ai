---
# pawrrtal-xahd
title: 'ci(paw): add GitHub Actions workflow for paw verify suites on PRs touching backend'
status: scrapped
type: task
priority: normal
created_at: 2026-05-27T20:02:35Z
updated_at: 2026-05-27T23:59:49Z
---

Task 9 of plan docs/superpowers/plans/2026-05-27-agent-cli-user.md ships the PAW_E2E=1 gate + subprocess fixture, but deferred the GitHub Actions workflow.

Wire a job that:
- Triggers on PRs touching backend/app/cli/paw/, backend/app/core/providers/, backend/app/api/
- Runs: cd backend && uv sync && PAW_E2E=1 OPENAI_API_KEY=\$secrets.OPENAI_API_KEY uv run pytest tests/e2e_paw/ -x -v
- Reports skipped vs failed clearly (don't fail the build if Codex creds absent)
- Maybe: nightly cron with the full live gate

## Reasons for Scrapping

Duplicate of pawrrtal-m20f. Work being done under m20f.

## Reasons for Scrapping

Duplicate of pawrrtal-m20f. Work being done under m20f.
