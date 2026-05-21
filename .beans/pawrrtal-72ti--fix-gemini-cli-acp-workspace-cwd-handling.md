---
# pawrrtal-72ti
title: Fix Gemini CLI ACP workspace cwd handling
status: completed
type: bug
priority: normal
created_at: 2026-05-21T12:04:32Z
updated_at: 2026-05-21T12:07:17Z
---

Gemini CLI ACP session/new fails when workspace.path is relative because the provider uses the same relative path for subprocess cwd and ACP cwd, causing Gemini to resolve workspaces/dev-admin/workspaces/dev-admin. Normalize cwd values to absolute paths and surface structured RequestError details.

## Summary of Changes

- Normalized Gemini CLI subprocess cwd and ACP session/new cwd through async path resolution so relative workspace paths do not get resolved twice by the CLI.
- Surfaced Gemini CLI structured RequestError details when present, so directory/config failures are not mislabeled as auth failures.
- Added regression tests for relative workspace cwd handling and structured session/new error details.

## Verification

- cd backend && uv run pytest tests/test_gemini_cli_provider.py
- cd backend && uv run ruff check app/core/providers/gemini_cli/acp.py app/core/providers/gemini_cli/provider.py tests/test_gemini_cli_provider.py
