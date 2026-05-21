---
# pawrrtal-1cfl
title: 'Active Recall: auto-search LCM before the main agent runs'
status: completed
type: epic
priority: high
created_at: 2026-05-19T07:15:14Z
updated_at: 2026-05-21T22:20:39Z
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

## Summary of Changes

- Implemented `PreTurnHook` plugins architecture.
- Added settings for active recall configuration (`active_recall_enabled`, `active_recall_model`, `active_recall_budget_seconds`, `active_recall_max_turns`).
- Created the Active Recall plugin at `backend/app/plugins/active_recall/` consisting of:
  - `plugin.py`: Registering pre-turn hooks.
  - `recall_agent.py`: Implementing a lightweight sub-agent that searches long-term memory via LCM tools.
- Integrated pre-turn hooks into `turn_runner.run_turn()`.
- Threaded recalled context into the main agent's system prompt when available.
- Added comprehensive unit and integration tests using `ScriptedStreamFn` for verifying sub-agent execution, tool limits, and timeouts.
- Wrote ADR docs for Active Recall and updated the handbook.
- Resolved Sentrux import fan-out architecture constraints.
