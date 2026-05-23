---
# pawrrtal-jjk8
title: Relocate Notion integration to plugins folder
status: completed
type: task
priority: normal
created_at: 2026-05-23T08:54:44Z
updated_at: 2026-05-23T08:54:52Z
---

Move all Notion integration files under backend/app/integrations/notion to backend/app/plugins/notion and update all imports to unify plugin structures.

## Summary of Changes
- Relocated files from `backend/app/integrations/notion/` to `backend/app/plugins/notion/`.
- Updated package-internal imports and docstrings in the relocated files.
- Adjusted startup integrations/plugins registration side effects.
- Updated core keys/env configuration and backend tests to target the new plugin module path.
- Updated frontend handbook documentation to align with the plugin path naming.
- Refactored Telegram bot logic to reduce fan-out dependency count to 15, resolving architectural gates.
- Resolved type-only imports and local import format warnings to satisfy Python Ruff linter rules.
