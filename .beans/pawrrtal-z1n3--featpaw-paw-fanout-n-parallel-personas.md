---
# pawrrtal-z1n3
title: 'feat(paw): paw fanout N — parallel personas'
status: in-progress
type: feature
priority: low
created_at: 2026-05-27T20:08:17Z
updated_at: 2026-05-28T00:58:09Z
parent: pawrrtal-6cnv
---

v2 paw command. N parallel personas hitting the same backend. Parent: pawrrtal-6cnv.

## Summary of Changes

Implemented `paw fanout N COMMAND...` as a local CLI orchestrator (not a backend feature).
`paw fanout 5 conversations send "hello" --new --model X` spawns 5 child `paw`
invocations in parallel, each with its own isolated config directory and a distinct
profile name, runs the wrapped command in each, aggregates stdout/stderr/exit codes,
and returns aggregate exit = max(child exit codes).

### Files

- `backend/app/cli/paw/commands/fanout.py` — new module. `fanout()` registered at
  top level via `app.command("fanout", context_settings={"allow_extra_args": True,
  "ignore_unknown_options": True})(fanout_cmd.fanout)`, same pattern as `record`/`replay`.
  Flags: `--max-concurrent`, `--json`, `--persona-prefix`, `--keep-personas`.
- `backend/app/cli/paw/main.py` — register the command.
- `backend/tests/paw/test_command_fanout.py` — 13 tests via monkeypatched
  `asyncio.create_subprocess_exec`; no real subprocesses spawned.
- `.claude/skills/paw/SKILL.md` — added `fanout` row to the Resource map and
  removed it from "Deferred to v2".

### Persona isolation

Each child subprocess receives:

- `PAW_CONFIG_DIR=<parent_config_root>/.fanout-<prefix>-<i>` — a per-slot directory
  that fully isolates cookies + persona state (the entire XDG-style config root for
  this child).
- `PAW_PROFILE=<prefix>-<i>` — slot profile name. Set on every child for forward
  compatibility / tools that read it directly; the existing CLI consumes profile
  via `--profile` per-command.
- All other env vars are inherited from the parent so DB / API URL config stays
  consistent across slots.

### Cleanup

By default the parent removes the per-slot directories it allocated after the run
finishes (only the directories matching the allocated paths — never user data).
`--keep-personas` skips cleanup so failed slots can be inspected.

### Tests (13, all passing)

- N=3 personas → 3 subprocess calls with distinct PAW_PROFILE / PAW_CONFIG_DIR
- Wrapped argv is forwarded verbatim to each child
- Aggregate exit = max(child exits) — a single exit=5 bubbles to parent exit=5
- `--max-concurrent 1` serializes (peak active children == 1, ordering preserved)
- `--json` output schema (list of {slot, profile, exit_code, stdout, stderr, duration_ms})
- Default cleanup removes per-slot dirs; `--keep-personas` leaves them
- `--persona-prefix` changes slot names
- Bare `paw fanout 3` (no wrapped command) → exit 1 LocalError
- Slot count 0 → exit 1 LocalError
- Slot count > MAX_SLOTS (256) → exit 1 LocalError
- `--help` renders cleanly
- Each child's PAW_CONFIG_DIR lives under the parent's config_root()
