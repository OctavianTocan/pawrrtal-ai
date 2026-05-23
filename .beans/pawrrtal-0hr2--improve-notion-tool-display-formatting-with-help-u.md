---
# pawrrtal-0hr2
title: Improve Notion tool display formatting with help, UUID, flag and stdin parsing
status: completed
type: task
priority: normal
created_at: 2026-05-23T15:54:35Z
updated_at: 2026-05-23T15:57:50Z
---

Improve ntn tool formatter in backend/app/plugins/notion/tool.py to filter global flags, parse help commands, extract UUIDs from API paths, parse short/inline flags, and indicate piped stdin. Verify with tests.

## Goal
Improve Notion tool display formatting for better user experience on Web and Telegram.

## Files
- `backend/app/plugins/notion/tool.py`
- `backend/tests/test_notion_plugin.py`

## Tasks
- [x] Filter global flags (e.g. `--json`, `-v`, `--verbose`) before subcommand parsing
- [x] Detect `-h`/`--help` flags and format with `ℹ️` icon and cleaner description
- [x] Support short flags (`-t`) and inline flag assignments (`--title=val`) in `pages create`
- [x] Extract and truncate UUIDs in `api` paths (e.g., `api/v1/pages/<uuid>`)
- [x] Add piped stdin indicator when stdin is provided
- [x] Add backend unit tests to verify the new display cases
- [x] Run backend verification tests and checks

## Summary of Changes
- Refactored `_format_ntn_display` in `backend/app/plugins/notion/tool.py` to filter global flags (`--json`, `--verbose`, `-v`, `--no-color`) prior to matching subcommands.
- Implemented `_parse_help_command` to detect `-h` / `--help` flags and return a clean help description with a `ℹ️` emoji.
- Extended the `pages create` parser to extract page titles passed via short option (`-t`), space separation, or inline flag assignment (`-t=title`, `--title=title`) and sanitized surrounding quotes.
- Added `_format_api_path` which uses a regular expression to match UUIDs inside raw API paths and truncates them for a cleaner display (e.g. `v1/pages/3673c065...`).
- Added a `(piped stdin)...` suffix mapping when the stdin payload is provided.
- Added `TestFormatter` in `backend/tests/test_notion_plugin.py` covering all formatting scenarios.
