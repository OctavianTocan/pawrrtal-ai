---
# pawrrtal-c1sx
title: Log Gemini CLI ACP activity
status: completed
type: task
priority: normal
created_at: 2026-05-21T12:09:28Z
updated_at: 2026-05-21T12:11:23Z
---

Add structured backend logs for Gemini CLI ACP updates and callbacks so operators can see what the CLI is doing during long turns, even when the UI only shows thinking/tool summaries.

## Summary of Changes

- Added INFO-level structured logs for every Gemini CLI ACP session update: agent text, thought text, tool starts, tool progress, usage updates, and metadata-only updates.
- Added structured logs for permission requests/approvals and workspace filesystem read/write callbacks.
- Kept log payloads bounded by logging character counts and compact snippets instead of full message/file contents.

## Verification

- cd backend && uv run ruff check app/core/providers/gemini_cli/client.py tests/test_gemini_cli_provider.py
- cd backend && uv run pytest tests/test_gemini_cli_provider.py
