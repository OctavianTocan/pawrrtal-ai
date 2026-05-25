---
name: paw-bootstrap
version: 2026-05-21
description: First-run setup for a new Pawrrtal workspace.
triggers: ["bootstrap", "first run", "new paw", "introduce yourself"]
tools: [workspace_files]
category: meta
---

# Paw Bootstrap

Use this skill when `PREFERENCES.md` has `bootstrap_completed: false`.

Ask one short opening question so the user can choose the Paw's name, voice, style, emoji, boundaries, or working preferences. If the user gives enough information in one message, proceed without extra interrogation.

When enough information is available, update `PREFERENCES.md`:

1. Rewrite only the JSON block between the identity markers.
2. Set `bootstrap_completed` to `true`.
3. Add concise freeform notes that reflect the user's stated preferences.

Do not say setup is complete until the write succeeds.
