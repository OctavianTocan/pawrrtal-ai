---
# pawrrtal-if8h
title: Improve Notion tool formatting for diagnostics, listings, and database APIs
status: completed
type: task
priority: normal
created_at: 2026-05-23T16:02:56Z
updated_at: 2026-05-23T16:07:43Z
---

Improve display formatting of doctor, pages list, api ls, and databases query/schema retrieval. Add pytest tests and verify code.

## Goal
Improve Notion tool display formatting for diagnostic and endpoint-related commands.

## Files
- `backend/app/plugins/notion/tool.py`
- `backend/tests/test_notion_plugin.py`

## Tasks
- [x] Add `doctor` diagnostic matcher
- [x] Add `pages list` command matcher
- [x] Add `api ls` endpoint listing matcher
- [x] Add `v1/databases/<db_id>/query` raw API matcher
- [x] Add `v1/databases/<db_id>` schema raw API matcher
- [x] Implement backend unit tests verifying the display cases
- [x] Verify changes against pytest and formatting checkers

## Summary of Changes
- Refactored `backend/app/plugins/notion/tool.py` to extract page creation and database API parsing into dedicated helpers (`_parse_pages_create`, `_parse_pages_update_append`, and `_parse_api_databases`), keeping cognitive complexity and return count within Python Ruff limits.
- Added formatter support for diagnostic diagnostics (`ntn doctor` -> `🩺 Running Notion diagnostics...` / `Ran Notion diagnostics`).
- Added formatter support for page listing (`ntn pages list` -> `📖 Listing Notion pages...` / `Listed Notion pages`).
- Added formatter support for API endpoint listing (`ntn api ls` -> `📋 Listing Notion API endpoints...` / `Listed Notion API endpoints`).
- Added formatter support for database queries (`api/v1/databases/<db_id>/query` -> `🔍 Querying Notion database <db_id_truncated>...` / `Queried Notion database <db_id_truncated>`).
- Added formatter support for database schemas (`api/v1/databases/<db_id>` -> `🗂️ Reading Notion database schema <db_id_truncated>...` / `Read Notion database schema <db_id_truncated>`).
- Appended unit tests covering the new format matchers in `backend/tests/test_notion_plugin.py`.
- Ran all verification tests, formatters, and architectural checks successfully.
