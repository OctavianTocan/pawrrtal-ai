---
# pawrrtal-gw5b
title: 'feat(paw): paw lcm + memories + dreaming'
status: in-progress
type: feature
priority: low
created_at: 2026-05-27T20:08:17Z
updated_at: 2026-05-28T00:49:12Z
parent: pawrrtal-6cnv
---

v2 paw command. LCM list/get + memories + dreaming. Parent: pawrrtal-6cnv.

## Summary of Changes

**Scope narrowed at implementation time.** The original bean covered `paw lcm` as a v2 catch-all for LCM CRUD + memories + dreaming. Investigation showed the backend currently exposes only one LCM HTTP endpoint — `GET /api/v1/lcm/conversations/{id}/context` (the debug observability surface in `backend/app/api/lcm.py`). Memories, lineages, and dreaming are not yet HTTP-reachable.

What shipped: `paw lcm context <conv-id> [--fresh-tail-count N]` — single read-only verb that returns the assembled pre-turn agent context (resolved messages + summaries with ordinals, roles, token estimates, depth/kind/source-count). Three output modes (human / `--json` / `--plain` TSV).

What's deferred: `paw lcm memories`, `paw lcm lineages`, `paw lcm dream` — blocked on the backend HTTP surface tracked in follow-up bean `pawrrtal-x9u4`. The skill's "Deferred to v2" section was updated to reflect this.

Files:
- `backend/app/cli/paw/commands/lcm.py` (new) — typer app + single `context` verb.
- `backend/app/cli/paw/main.py` — registers `lcm_cmd.app` under `paw lcm`.
- `backend/tests/paw/test_command_lcm.py` (new) — 11 tests covering JSON / human / plain modes, query-param forwarding, validation, and 401/404/500 error mapping.
- `.claude/skills/paw/SKILL.md` — Resource map row added; deferred section narrowed to the remaining surface.

Verification: `tests/paw/test_command_lcm.py` 11/11 green. Full `tests/paw` suite 202/202 green (191 prior + 11 new). `ruff check` + `mypy` clean on the new file. `paw lcm --help` and `paw lcm context --help` render correctly.
