---
# pawrrtal-vd6e
title: Fix PR 262 CI and review feedback
status: in-progress
type: bug
priority: normal
created_at: 2026-05-17T11:22:32Z
updated_at: 2026-05-17T12:01:50Z
---

Track CI/review follow-up for PR 262 until all checks and actionable reviews are green.


## Updates

- Fixed the sentrux god-file violation by moving workspace prompt assembly behind `app.channels._turn_workspace`.
- Preserved the old `_workspace_system_prompt` import path as a compatibility wrapper for existing tests.

## Verification

- `just sentrux` passed locally.
- `uv run ruff check backend/app/channels/turn_runner.py backend/app/channels/_turn_workspace.py` passed.
- `env AUTH_SECRET=test-secret GOOGLE_API_KEY=test-key WORKSPACE_ENCRYPTION_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= CORS_ORIGINS='["http://localhost:3001"]' uv run pytest tests/test_agent_system_prompt.py tests/test_observability_workshop.py tests/test_verbose_filter.py` passed: 43 tests.\n


## CI Failure Fix

- Moved provider-facing display-map helpers from `app.core.tools.display` to `app.core.agent_loop.display` so providers stay tool-agnostic.
- Kept `tools.display` as the tool formatter/summarization module and re-exported safe fallback helpers needed by tests.

## Additional Verification

- `python3 scripts/check-no-tools-in-providers.py` passed.
- Focused backend display/provider tests passed: 93 tests.
- `just check` passed.
- `git diff --check` passed.
