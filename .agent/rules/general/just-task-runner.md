---
name: just-task-runner
paths: ["**/*"]
---

# Use `just` Task Runner

When a project has a `justfile`, use `just` for all project operations instead of raw commands. `just test`, `just lint`, `just build` — not `pnpm vitest`, `pnpm biome check`, etc.

**Why:** Justfiles encode the canonical way to run project tasks. They abstract away package manager differences, environment setup, and flag variations. If a task isn't in the justfile, add it there first.

**Learned from:** pawrrtal (OctavianTocan/pawrrtal) — project convention.

## Verify

"Does this project have a justfile? Am I using `just` commands instead of raw package manager commands?"

## Patterns

Bad — raw commands bypass justfile conventions:

```bash
pnpm vitest run src/auth.test.ts
pnpm biome check --fix src/
pnpm tsc --noEmit
// Flags and setup may differ from what the team uses
```

Good — justfile tasks ensure consistency:

```bash
just test src/auth.test.ts
just lint
just typecheck
// Same flags, same setup, same behavior for everyone
```
