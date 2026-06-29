---
name: readme
paths: [".no-match"]
---

# Path-scoped rules (Pawrrtal brain)

**Canonical:** `.agent/rules/` in the portable brain. Harness symlinks: `.claude/rules`, `.agents/rules`.

Onboarding index: `CURATED.md`. Authoring guide: `AGENTS.md`. Skill: `path-rules`.

Vendored from [claude-rules](https://github.com/OctavianTocan/claude-rules). Every rule exists because something went wrong without it.

## Quick start (global install — optional)

```bash
git clone git@github.com:OctavianTocan/claude-rules.git ~/.claude/rules
```

In **this repo**, edit `.agent/rules/` — do not rely on a global `~/.claude/rules` copy.

## Categories

| Category | Count | When it fires |
| --- | --- | --- |
| **ci/** | 49 | Editing `.github/workflows/`, `Dockerfile`, shell scripts |
| **typescript/** | 17 | Editing `.ts`/`.tsx` files |
| **react/** | 19 | Editing `.ts`/`.tsx` files |
| **debugging/** | 18 | Always (general methodology) |
| **brownfield/** | 15 | Editing native/RN brownfield files |
| **git/** | 12 | Editing `.github/` configs, shell scripts |
| **twinmind/** | 10 | Editing app-specific `.ts`/`.tsx`/native files |
| **react-native/** | 11 | Editing `.ts`/`.tsx`/`.kt`/`.java`/`.swift` files |
| **testing/** | 8 | Editing test files |
| **state-management/** | 6 | Editing `.ts`/`.tsx`/native files |
| **error-handling/** | 8 | Editing `.ts`/`.tsx` files |
| **api/** | 4 | Editing `.ts`/`.tsx`/`.js` files |
| **auth/** | 4 | Editing `.ts`/`.tsx` files |
| **sweep/** | 4 | Editing source files (AI review patterns) |
| **general/** | 14 | Always |
| **monorepo/** | 4 | Editing `package.json`, `pnpm-workspace.yaml` |
| **expo/** | 3 | Editing Expo config and entry files |
| **e2e/** | 3 | Editing Maestro/Android test files |
| **figma/** | 5 | Editing `.ts`/`.tsx`/`.css` files |
| **playwright/** | 5 | Editing Playwright test/config files |
| **rust/** | 3 | Editing `.rs` files |

## Rule format

Every rule has YAML frontmatter with `name` and `paths`:

```markdown
---
name: no-unwrap-in-production
paths: ["**/*.rs"]
---

# No unwrap() in Production Rust

Explanation of what goes wrong and why.

## Verify
"Am I using unwrap() anywhere? Can this fail at runtime?"

## Bad
...code example...

## Good
...code example...
```

Claude Code loads rules matching the current file's path against the `paths` globs. General rules with `["**/*"]` fire on every file.

## Writing new rules

1. Pick the right category directory (or create one)
2. File name = kebab-case summary of the rule
3. Add `name:` (kebab-case slug) and `paths:` (glob array)
4. Include: what goes wrong, why, bad/good examples, and a Verify question
5. Commit with `feat:` prefix

## Origin

Rules extracted from real projects:

- **tap** — Rust Telegram bot / multi-agent gateway (provider traits, subprocess testing)
- **pawrrtal** — TypeScript full-stack app (Biome, multi-agent git safety)
- **openclaw-notion/todoist** — Agent plugins (per-agent auth, test isolation)
- CI pipelines across self-hosted Mac Mini runners, GitHub Actions, and Gradle builds

## License

Personal use.
