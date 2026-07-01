---
name: path-rules
description: "Use when creating, editing, pruning, or curating path-scoped rule files under .agent/rules/. Covers YAML paths frontmatter, category layout, CURATED.md, and harness symlinks (.claude/rules, .agents/rules)."
---

# Path-scoped rules

## Canonical location

| Path | Role |
|------|------|
| **`.agent/rules/`** | Portable brain — edit here |
| `.claude/rules` | Symlink → `.agent/rules` (Claude Code loader) |
| `.agents/rules` | Symlink → `.agent/rules` (Codex discovery) |
| `.cursor/plugins/pawrrtal/rules/` | Cursor `.mdc` — Pawrrtal-specific (clean-code, github-actions) |
| `.cursor/rules/` | Cursor always-on / vendored rules (e.g. stagehand) |

## What goes where

| Surface | Holds |
|---------|--------|
| `.agent/rules/**/*.md` | Path-scoped traps with `paths:` globs — one incident per file |
| `.agent/rules/CURATED.md` | Onboarding reading list (highest-signal rules) |
| `.agent/rules/AGENTS.md` | Authoring philosophy, naming, frontmatter |
| `skills/code-quality` | Cross-stack summary while coding |
| `memory/semantic/LESSONS.md` | Graduated one-liners from `learn.py` / `graduate.py` |
| Linter configs | Enforceable checks — not duplicate rules |

**Do not** paste full rule bodies into AGENTS.md or skills — link or curate.

## Rule file shape

```yaml
---
name: kebab-case-slug
paths: ["**/*.{ts,tsx}"]
---

# Complete sentence title

Failure mode + fix. ## Verify section required. Bad/good examples.
```

See `.agent/rules/AGENTS.md` for categories, naming, and anti-patterns.

## Editing checklist

- [ ] New trap from a real incident → new `.md` in the right category folder
- [ ] `paths:` globs match files this repo actually ships
- [ ] Under ~80 lines; split if two traps
- [ ] High-signal onboarding pick → add row to `CURATED.md`
- [ ] Pawrrtal-only + Cursor plugin → `.cursor/plugins/pawrrtal/rules/` (`.mdc`)
- [ ] Upstream vendored rule → sync from `OctavianTocan/claude-rules` when porting

## Harness notes

- Claude Code loads `.md` with `paths:` when editing matching files
- `.agent/rules/cursor-vendored/` is a **reference snapshot** of `.mdc` files — zero Claude context cost
- Cursor plugin rules were **moved out** of this tree; Claude does not auto-load them from `.agent/rules`
