# Writing Plans

Quality conventions for implementation plans. This reference defines the format, structure, and quality bar for both the overall plan and per-step detail files. Plans assume the implementing agent has zero context: document everything needed, give exact file paths, full code blocks, and verification commands.

## Overall Plan Format

The overall plan is the high-level document saved to `docs/plans/YYYY-MM-DD-<name>.md`. It provides the big picture and references detailed per-step files.

```markdown
# [Feature Name] Implementation Plan

> **For agentic workers:** Execute this plan task-by-task.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

## Overview

[How all steps fit together, data flow, key design decisions]

## Packages & Files Affected

[Grouped by package — every file to create/modify/delete]

backend-ts/apps/api/
  - Modify: src/Modules/Projects/Service.ts — add project behavior
  - Modify: src/Modules/Projects/Repo.ts — persist project state
  - Test:   test/unit/Modules/Projects/Service.test.ts

frontend/features/nav-chats/
  - Modify: components/NavChats.tsx — surface project state in the sidebar
  - Test:   __tests__/nav-chats.test.tsx

## Execution Order

[Which steps are independent, which depend on others]
[Visual dependency graph if helpful]

## Step 1: [Name]
**Depends on:** none
**Parallel:** [yes/no — can run alongside other independent steps]
**Detail:** .context/plans/step-1-<name>.md
**Summary:** [2-3 sentences of what this step does]
**Decomposition hint:** [optional — "straightforward" | "consider sub-steps for X"]

## Step 2: [Name]
**Depends on:** Step 1
**Detail:** .context/plans/step-2-<name>.md
**Summary:** [2-3 sentences]

## Step N: ...
```

The overall plan is a **readable overview** that references the detailed step files. An executor sub-agent gets both the overview (to understand context) and their specific detail file (to know exactly what to do).

## Step Detail File Format

Each step gets a detail file at `.context/plans/step-N-<name>.md`. These are the actionable implementation specs that executor sub-agents work from.

````
# Step N: [Name]

**Goal:** [One sentence]
**Depends on:** [Step numbers or "none"]

## Files

- Create: `exact/path/to/new-file.ts` — purpose
- Modify: `exact/path/to/existing-file.ts` — what changes
- Test: `exact/path/to/test-file.test.ts`

## Implementation

### N.1: [Sub-task name]

[Complete code blocks with full implementation — not descriptions of code]

```typescript
// Full implementation here
```

**Verify:**
Run: `bun run test --filter=<package>`
Expected: [exact expected output]

**Commit:**
```bash
git add [specific files]
git commit -m "<scope>: <imperative summary>"
```

### N.2: [Sub-task name]
...

## Decomposition Hint

[Optional guidance for the executor sub-agent]
- "Straightforward — direct execution expected"
- "Large scope (N files across M packages) — consider per-package sub-steps"
- "Complex logic in X — may warrant further decomposition"

The executor confirms and adjusts at runtime based on what it finds.
````

## Step Detail Quality Checklist

Every step detail file must pass these checks:

- [ ] **Exact file paths.** Use monorepo conventions: PascalCase for backend modules (`Modules/Users/Domain.ts`), kebab-case for frontend (`components/user-profile.tsx`), tests in `test/` directories.
- [ ] **Complete code, not descriptions.** Write `export class NotFoundError extends Schema.TaggedError<NotFoundError>()("NotFoundError", { id: Schema.String }) {}`, not "add a not-found error."
- [ ] **Explicit dependencies.** If Step 3 needs types from Step 1, say so. Order steps so each builds on the last.
- [ ] **Verification step.** Each sub-task includes a run command with expected output.
- [ ] **Commit message.** Each sub-task ends with a commit following `<scope>: <imperative summary>` format.
- [ ] **Decomposition hint.** Include guidance for the executor on whether to decompose further.

## Dependency Declaration

Steps have three dependency types:

- **Hard dependency** — Step B literally cannot execute without Step A's output (e.g., B imports types defined in A). Mark as `**Depends on:** Step A`.
- **Soft dependency** — Step B is easier to write after Step A exists but could technically be written independently. Note in the description but do not block on it.
- **No dependency** — Steps can run in parallel. Mark as `**Parallel:** yes`.

Hard dependencies determine execution order. No-dependency steps are candidates for parallel sub-agent execution.

## Convention Reminders

Plans must follow all AGENTS.md conventions. Common ones to check:

- Frontend path aliases use the repo's local conventions; backend-ts packages use `@pawrrtal/api` and `@pawrrtal/api-core`
- Frontend code talks to the backend only through established API endpoints (`useAuthedFetch` or TanStack Query mutations)
- No file extensions in imports (no `.ts`, `.tsx`, `.js`)
- `Schema.TaggedError` with `_tag` for backend errors
- Backend-ts Effect API checks use `backend/vendor/effect-smol`, not Effect v3 docs
- Tests in `test/` directory, not co-located
- Named exports (default only for Next.js pages/layouts)
- No type casting (`as`, `as any`, etc.) — fix the underlying type
- Effect-TS projects use idiomatic Effect patterns (`Effect.gen`, `pipe`, `Layer`, `Service`, `Schema`)
