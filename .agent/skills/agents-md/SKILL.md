---
name: agents-md
description: "Use when creating, editing, restructuring, or reviewing AGENTS.md files or the CLAUDE.md symlink. Covers Pawrrtal's two-tier layout, what belongs in AGENTS.md vs memory vs skills, and line budgets."
---

# AGENTS.md authoring

## Two-tier layout

| File | Role |
|------|------|
| **Root `AGENTS.md`** | Stub (~10 lines) → points to `.agent/AGENTS.md` |
| **`.agent/AGENTS.md`** | Entry contract — bootstrap, non-negotiables, memory map |
| **`CLAUDE.md`** | Symlink to root stub |
| **Nested `AGENTS.md`** | Package-local overrides |

## What goes where

| Surface | Holds |
|---------|--------|
| `.agent/AGENTS.md` | Read order, hard safety lines, where depth lives, brain map |
| `memory/personal/PREFERENCES.md` | How the user works — taste, workflow, multi-agent |
| `memory/semantic/DOMAIN_KNOWLEDGE.md` | Stable facts — ports, commands, structure, auth |
| `memory/semantic/LESSONS.md` | Graduated lessons (`learn.py` / `graduate.py`) |
| `memory/semantic/DECISIONS.md` | Major brain/architecture choices |
| `skills/*` | Procedures (`repo-operations`, `code-quality`, …) |
| `rules/**` | Path-scoped file traps (`paths:` globs) |
| `.cursor/plugins/pawrrtal/rules/` | Cursor `.mdc` (clean-code, github-actions) |
| `protocols/permissions.md` | Tool safety (non-negotiable) |

**Do not put preferences or commands in AGENTS.md** — that duplicates memory. AGENTS.md only **points** to them.

## Line budgets

- Root stub: ≤ 15 lines
- `.agent/AGENTS.md`: ≤ 120 lines (orchestration only)
- `DOMAIN_KNOWLEDGE.md`: facts, no taste
- `PREFERENCES.md`: taste and workflow, no ports

## Required in `.agent/AGENTS.md`

1. Session bootstrap (read order including DOMAIN_KNOWLEDGE)
2. Non-negotiables (~6 bullets)
3. "Where depth lives" table
4. Memory map + review queue summary
5. CLI tools + brain rules

**Not** in AGENTS.md: full command lists, Always/Ask/Never essays, code examples, user UI taste.

## Editing checklist

- [ ] New **fact** (port, route, term) → `DOMAIN_KNOWLEDGE.md`
- [ ] New **taste/workflow** → `PREFERENCES.md`
- [ ] New **learned habit** → `learn.py` or `graduate.py`
- [ ] New **procedure** → skill (`repo-operations`, etc.)
- [ ] AGENTS.md only gets a new row in "Where depth lives" if needed

```bash
wc -l AGENTS.md .agent/AGENTS.md memory/personal/PREFERENCES.md memory/semantic/DOMAIN_KNOWLEDGE.md
```

## Anti-patterns

| Don't | Do |
|-------|-----|
| Paste preferences into AGENTS.md | `PREFERENCES.md` |
| Paste commands/ports into AGENTS.md | `DOMAIN_KNOWLEDGE.md` |
| Duplicate in `workspace-context` skill | Point at memory files |
| Grow root stub | Edit `.agent/` + memory |
