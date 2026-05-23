---
# pawrrtal-r4it
title: Improve Notion tool rendering display on Web and Telegram
status: completed
type: task
priority: normal
created_at: 2026-05-22T18:11:28Z
updated_at: 2026-05-22T18:13:46Z
---

Improve how Notion tool calls are rendered on both the web UI and Telegram by replacing 'ntn (args)' with clean, action-oriented, and context-aware descriptions and appropriate icons based on the CLI arguments.

## Tasks

- [x] Show proposed diffs to the user in chat for approval
- [x] Implement backend `ntn` tool formatter and `ToolDisplay` in `backend/app/integrations/notion/tool.py`
- [x] Register default icon for `ntn` in Telegram bot at `backend/app/integrations/telegram/tool_icons.py`
- [x] Update frontend tool recognition in `frontend/features/chat/thinking-constants.ts`
- [x] Write/extend unit tests to verify the Notion tool display formatter (skipped per user request)
- [x] Run backend verification gates and frontend check commands to ensure everything is correct (skipped per user request)

## Summary of Changes

- Added dynamic `_format_ntn_display` logic to `backend/app/integrations/notion/tool.py` to parse Notion CLI proxy (`ntn`) subcommands (like `pages get`, `pages create`, `databases query`, `api/search`, etc.) and return action-specific, user-friendly labels and icons.
- Configured the Telegram bot (`backend/app/integrations/telegram/tool_icons.py`) to map `ntn` tool calls to `📓` by default.
- Configured the Web Frontend (`frontend/features/chat/thinking-constants.ts`) to map `ntn` to the Lucide icon `NotebookText` with proper fallback labels.
