---
# pawrrtal-9iae
title: 'Active Recall step 1: add active_recall_* settings flags'
status: completed
type: task
priority: high
created_at: 2026-05-19T07:16:01Z
updated_at: 2026-05-19T07:41:38Z
parent: pawrrtal-1cfl
---

## Goal

Add on/off knobs for Active Recall.

## File

`backend/app/core/config.py` — right next to the existing `lcm_*` settings.

## Add these settings

| Setting | Type | Default | What it does |
|---|---|---|---|
| `active_recall_enabled` | `bool` | `False` | Master switch |
| `active_recall_model` | `str` | `""` | Helper's model (`""` = default fast/cheap, e.g. Gemini Flash Lite) |
| `active_recall_max_iterations` | `int` | `3` | How many tool calls the helper can make |
| `active_recall_max_wall_clock_seconds` | `float` | `15.0` | How long the helper can run |
| `active_recall_max_summary_chars` | `int` | `600` | Max length of the note it returns |

Each is also readable from a matching env var (`Settings` already does this via `BaseSettings`).

## After

```bash
cd backend && uv run ruff check
```
