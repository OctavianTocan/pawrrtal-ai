---
name: code-quality
description: "Use when writing or reviewing Pawrrtal code: naming booleans and callbacks, shaping function signatures, adding TSDoc/JSDoc, splitting files, choosing readonly params, or deciding how to verify a change. Covers frontend (Next.js/TS), Python backend, and backend-ts Effect strangler. Stack-specific skills refine these rules."
---

# Pawrrtal Code Quality

Day-to-day patterns for readable, maintainable code across Pawrrtal's three stacks:

| Stack | Where it lives | Deeper skills |
|---|---|---|
| Frontend | `frontend/` — App Router, `features/`, TanStack Query | `vercel-react-best-practices`, `user-facing-text`, `taste` |
| Python backend | `backend/app/` — FastAPI, SQLAlchemy, providers/tools | `python-testing-patterns`, `returns`, `extension-boundaries` |
| Effect strangler | `backend-ts/` — HttpApi, Repo/Service/Http layers | `domain-effect` |

Hard gates (explicit return types, no unsafe casts, sentrux layers, 500-line file ceiling, nesting budget, preserve docs, run toolchain after writes) live in `AGENTS.md` and `.cursor/plugins/pawrrtal/rules/`. This skill is the authoring delta agents apply while editing.

## Quick Reference

| Area | Rule |
|---|---|
| Booleans | Verb prefix: `is*`, `has*`, `can*`, `should*`. Never negative. No boolean positional params — use an options object. |
| React callbacks | Props: `on*`. Implementations: `handle*`. |
| Constants | `UPPER_SNAKE_CASE` for env/config/fixed domain limits; else `camelCase`. |
| Parameters | Max **3** positional. Fourth+ goes in an options object. `(id, input)` or `(id, options?)`. |
| Return types | **Every** function — exported or not — gets an explicit return type. |
| Immutability | Default `readonly` for array/object params the function does not mutate. |
| Function shape | Guard clauses at top, happy path at bottom. Braces on all `if`. Max **3** nesting levels. |
| Files | One concept per file. CI hard-stops at **500** lines; split earlier when the name needs "and". |
| Type declarations | Prefer `type`; `interface` for `extends`/declaration merging or `declare module`. |
| Errors | Never fire-and-forget. Handle the specific failure; surface user-facing copy via `user-facing-text`. |
| Verify | `just check` + scoped typecheck/tests. Gate on **exit codes**, not grepped output. |

## Naming

### Booleans

Verb prefix — no bare adjectives or nouns:

| Prefix | Meaning | Examples |
|--------|---------|----------|
| `is*` | Current state | `isLoading`, `isOpen`, `isValid` |
| `has*` | Existence | `hasError`, `hasMessages`, `hasPermission` |
| `can*` | Capability | `canEdit`, `canSubmit`, `canStream` |
| `should*` | Conditional behavior | `shouldValidate`, `shouldRetry`, `shouldRender` |

Never negative (`isNotReady`); invert. Derived booleans keep the prefix:

```typescript
// Good
const canSubmit = isValid && !isLoading;

// Bad — bare adjective
const loading = query.status === "pending";
```

### React callbacks

Match repo React rules: callback **props** are `onSomething`, local **handlers** are `handleSomething`. Do not mix them on the same surface.

### Constants

`UPPER_SNAKE_CASE` for environment variables, config keys, and fixed domain limits (`MAX_RETRIES`, `DEFAULT_PAGE_SIZE`). `camelCase` for everything else. See `.cursor/plugins/pawrrtal/rules/clean-code/named-constants.mdc`.

### User-facing strings

Tool names, buttons, status lines, and error copy are Title Case with spaces (`List Folder`, not `list_folder`). See `user-facing-text`.

## Function Structure

### Early returns

Guard clauses at the top, happy path at the bottom. Never bury the main path inside nested `if/else`. All `if` statements use braces. Nesting beyond three compound levels (`if`/`for`/`while`/`try`/`switch`) fails CI — extract helpers instead.

```typescript
function finalizeTurn(turn: TurnState): TurnResult {
  if (!turn.isValid) {
    return TurnResult.invalid(turn.id);
  }
  if (turn.isCancelled) {
    return TurnResult.cancelled(turn.id);
  }
  if (!turn.hasProvider) {
    return TurnResult.missingProvider(turn.id);
  }

  const output = runPipeline(turn);
  return TurnResult.success(output);
}
```

### Single responsibility

One job per function. Biome flags cognitive complexity via `noExcessiveCognitiveComplexity` — when it fires, extract; do not widen suppressions.

### Delegate, don't duplicate

When an action and a guard share conditions, the action calls the guard:

```typescript
export function publishConversation(conversation: Conversation): PublishResult {
  if (!canPublish(conversation)) {
    return PublishResult.error("Cannot publish");
  }
  return doPublish(conversation);
}
```

### Parameters

- Max **3** positional parameters. A fourth value belongs in an options object.
- Destructure when reading **2+** properties from the same object. Single-property access does not need destructuring.
- No boolean positional parameters — they hide meaning at call sites. Use `{ immediate: true }` instead.

| Pattern | When | Example |
|---------|------|---------|
| `(input)` | Create with required data | `create(input: CreateProjectInput)` |
| `(id)` | Single-entity read/delete | `get(id: ProjectId)` |
| `(id, input)` | Update with required data | `update(id: ProjectId, input: UpdateProjectInput)` |
| `(id, options?)` | Read with optional config | `get(id: ProjectId, options?: GetProjectOptions)` |
| `(options?)` | List/query with filters | `list(options?: ListProjectsOptions)` |

Required payload uses `input`; optional config uses `options`. Event payloads may use `payload`; HTTP query objects may use `params` where the module already does.

## Documentation

### TSDoc / JSDoc (TypeScript)

Every function — exports **and** private helpers — gets a doc block that describes the **interface** (what callers pass and receive), never the implementation (algorithms, storage, downstream calls).

- **Exported surfaces** (components, hooks, lib helpers, Effect services): summary line plus `@param` for every parameter, `@returns` for non-void returns, and `@template` / `@throws` where they carry contract. Required even when types look obvious.
- **Private helpers**: single-line summary only — no `@param`/`@returns` boilerplate.
- **Interface properties**: inline `/** */` above each field, not `@property` block tags.

Placement: directly above the declaration. Preserve existing docstrings when editing — update or delete only when the documented code changes. See `.cursor/plugins/pawrrtal/rules/clean-code/preserve-documentation.mdc`.

### Python docstrings

Public classes and functions get docstrings describing caller contract. Type hints on every function. Narrow `except` to specific types; log with context. See `.cursor/plugins/pawrrtal/rules/clean-code/python-logging-exceptions.mdc`.

### Inline comments

Explain non-obvious **WHY**, never restate **WHAT**. If the code already reads clearly, delete the comment. Cap at 1–2 lines. No PR/ticket references — that belongs in the commit message.

## Type Declarations

Prefer `type` for first-party declarations. Use `interface` for object shapes that `extend` or need declaration merging, and for `declare module`. Unions, mapped, conditional, and derived types require `type`. Derive from source (`z.infer`, Pydantic models, SQLAlchemy schemas, Effect `Schema.Type`) instead of hand-duplicating fields.

No unsafe casts (`as any`, double casts). Fix the underlying type. No TypeScript enums — use unions or `as const` objects.

## Return Types

| Context | Annotate? |
|---------|-----------|
| Every TS/TSX function | **Always** — Pawrrtal rule, not export-only |
| Python functions | Type hints on parameters and return |

Hooks, server actions, and Effect services follow the same rule: the signature documents the contract.

## Immutability

Default to `readonly` for array and object parameters the function does not mutate:

```typescript
export function summarizeMessages(messages: readonly Message[]): Summary;
export function applyTheme(theme: Readonly<ThemeTokens>): void;
export function shuffleIds(ids: string[]): void; // intentionally mutates
```

React: prefer immutable updates; avoid redundant mirrored state. See `.cursor/plugins/pawrrtal/rules/clean-code/avoid-redundant-state.mdc`.

## File Organization

A **concept** is a component family, hook module, service, repo, or utility group. Multi-file features belong in a **package directory** (`frontend/features/<feature>/`, `backend/app/providers/<provider>/`, `backend-ts/.../Modules/<Name>/`) — not flat siblings with redundant prefixes.

Within a file: imports → types/constants → main exports → internal helpers. Blank lines between groups.

Split when:

- The file approaches **500** lines (CI fails above this).
- The filename needs "and".
- Tests need heavy setup for a single unit.
- You cannot describe the file in one sentence.
- Sentrux reports a layer violation — fix structure, do not bypass with clever imports.

Icons and SVGs live in dedicated files; components import them. Never inline glyph markup in feature components.

## Readability

- **Explaining variables.** Name compound conditions (`isRecentConversation`, `hasPendingToolCall`) even when used once.
- **Declare near first use.** Do not stack unrelated `const` declarations at the top of a long function.

## Tests

Test through public interfaces — behavior that should survive refactors. Every assertion encodes **intent** (what must stay true), not incidental implementation detail.

| Stack | Where | Run |
|---|---|---|
| Frontend | colocated `*.test.ts(x)` under `frontend/` | `cd frontend && bun run test -- <pattern>` |
| Python | `backend/tests/` | `cd backend && uv run pytest <path>` |
| Effect TS | `backend-ts/apps/api/test/unit/` mirroring `src/` | follow `domain-effect` |

Agent-loop backend tests use scripted stream fns. Vitest strips types at runtime; run the suite after changing assertions.

## Verifying Changes

A check counts only when its **exit code** proves the thing.

```bash
just check                              # Biome repo-wide
cd frontend && bun run typecheck        # TS frontend
cd backend-ts && bun run typecheck      # Effect strangler (when touched)
just sentrux                            # architecture layers (when structure changes)
# plus scoped tests for the files you edited
```

- **Gate on exit codes**, not grepped tool output. Biome emits `lint/complexity/noExcessiveCognitiveComplexity` — pattern-matching stdout misses it.
- **Lint changed files on the PR that introduces them.** A violation can hide until the file is touched.
- **Fix warnings in files you edit.** Biome warnings and console warnings are latent errors — do not label them "pre-existing."
- When local and CI disagree, the clean CI run on the self-hosted runner is ground truth.

## Error Handling

Every async path handles failure and surfaces feedback — never fire-and-forget `void` promises.

| Stack | Pattern |
|---|---|
| Frontend | TanStack Query error states, toasts, inline error copy; `useAuthedFetch` for API calls |
| Python routes | `HTTPException` at the boundary; domain exceptions from `app/exceptions.py` and per-domain modules |
| Python internals | Narrow `except`; no `returns` / railway types — see `returns` |
| Effect TS | Tagged errors, `Effect.catchTag`, honest error channels in HttpApi handlers |

If a function can fail, the return type or error channel says so. User-visible messages follow `user-facing-text`.
