---
# pawrrtal-1cfl
title: 'Active Recall: auto-search LCM before the main agent runs'
status: in-progress
type: epic
priority: high
created_at: 2026-05-19T07:15:14Z
updated_at: 2026-05-19T07:41:37Z
---

## What this is

Make the AI quietly look through old chat memory **before** it answers, so it "remembers" relevant past stuff without being asked.

## How it works

1. You send a message.
2. Before the main AI replies, a tiny **helper AI** runs first.
3. The helper can only use the long-term memory tools: `lcm_grep`, `lcm_describe`, `lcm_expand_query`.
4. Tight budget: **3 tries max**, **15 seconds**, on a fast cheap model.
5. Helper returns one of:
   - a short note (≤600 chars) of what it found, or
   - the literal word `NONE`.
6. If it returned a note, we paste it into the main AI's system prompt so the main AI sees it.

## Rules

- **Off by default.** Flag: `active_recall_enabled`.
- **Never breaks the main turn.** Any failure → log a warning, pretend it returned `NONE`.
- Lives at `backend/app/plugins/active_recall/`.

> Inspired by OpenClaw's Active Memory.
