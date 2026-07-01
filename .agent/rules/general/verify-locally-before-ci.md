---
name: verify-locally-before-ci
paths: ["**/*"]
---

# Verify Locally Before CI

Run the project's full local verification suite before pushing to CI. Don't use CI as your test runner.

## Rule

Before `git push`:

1. Run the unified gate: `just check` (ruff + Biome)
2. Run type checks: `bun run typecheck`
3. Run tests: `just test` (pytest) and/or `bun run test`
4. Full gate before pushing: `just check-all` (ruff + Biome + bandit + mypy)

If touching only frontend, `just check` + `bun run typecheck` is the fast loop.

## Why

Each CI run costs time and money. A CI failure that could've been caught locally wastes 5-30 minutes of pipeline time and blocks other PRs. On self-hosted runners, it also blocks the physical machine for other team members.

## Verify

"Did I run the full local check suite before pushing? Could this failure have been caught locally?"

## Patterns

Bad — push without local verification:

```bash
git add -A && git commit -m "feat: new feature" && git push
# CI fails: type error on line 42
# 15 minutes wasted, runner blocked for the team
```

Good — local verification first:

```bash
just check          # biome + ruff (fast)
bun run typecheck   # tsc --noEmit
just test           # pytest
git add -A && git commit -m "feat: new feature" && git push
# CI passes on first try
```
