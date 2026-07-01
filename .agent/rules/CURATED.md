# Curated path rules (Pawrrtal)

Highest-signal defaults for this Next.js + FastAPI + Biome + Bun stack. The full `.agent/rules/` tree has additional coverage; this is the recommended reading order for onboarding.

Each rule below lives at the cited path with `paths:` frontmatter, so Claude only loads it when working on a matching file. To force-load one, ask the agent to read it.

## Debugging & incidents

- `.agent/rules/general/read-data-before-theory.md`
- `.agent/rules/general/diagnose-before-workaround.md`
- `.agent/rules/general/stop-after-two-failed-fixes.md`
- `.agent/rules/debugging/compare-working-vs-broken-before-fixing.md`

## TypeScript

- `.agent/rules/typescript/never-bypass-type-system-with-any-or-unsafe-cast.md`
- `.agent/rules/typescript/explicit-return-types-everywhere.md`
- `.agent/rules/typescript/validate-boundaries.md`
- `.agent/rules/typescript/discriminated-unions.md`
- `.agent/rules/typescript/function-signatures-must-be-honest.md`
- `.agent/rules/typescript/use-direct-named-imports-not-namespace.md`

## React (client UI)

- `.agent/rules/react/avoid-stale-closures-and-mutating-state.md`
- `.agent/rules/react/use-primitive-values-as-effect-dependencies.md`
- `.agent/rules/react/purity-in-memo-and-reducers.md`
- `.agent/rules/react/stable-keys.md`
- `.agent/rules/react/request-id-cancellation.md`
- `.agent/rules/react/portal-escape-overflow.md`

## API & fetch boundaries

- `.agent/rules/api/validate-response-shape-at-boundary.md`
- `.agent/rules/api/abort-controller-per-request.md`
- `.agent/rules/error-handling/check-response-before-parse.md`

## Auth (sessions/tokens)

- `.agent/rules/auth/deduplicate-concurrent-token-refreshes.md`
- `.agent/rules/error-handling/timeout-async-auth.md`

## Errors & async

- `.agent/rules/error-handling/abort-error-is-expected.md`
- `.agent/rules/error-handling/reset-flags-in-finally.md`
- `.agent/rules/error-handling/catch-promise-chains.md`

## Testing

- `.agent/rules/testing/vi-hoisted-for-mock-variables.md`
- `.agent/rules/testing/factory-over-shared-mutable.md`
- `.agent/rules/testing/test-isolation-ephemeral.md`
- `.agent/rules/testing/agent-loop-testing-philosophy.md` — backend agent-loop & StreamFn tests
- `.agent/rules/playwright/web-first-assertions.md`
- `.agent/rules/playwright/role-selectors.md`
- `.agent/rules/playwright/no-networkidle.md`

## Monorepo & Biome

- `.agent/rules/monorepo/single-lockfile-per-workspace.md`
- `.agent/rules/monorepo/biome-version-aware-config.md`
- `.agent/rules/general/biome-2-migration-gotchas.md`

## Git & PRs

- `.agent/rules/git/one-concern-per-pr.md`
- `.agent/rules/git/conventional-commits.md`

## AI review / sweep

- `.agent/rules/sweep/read-type-signatures-before-use.md`
- `.agent/rules/sweep/review-comments-are-patterns.md`

## Vendored Cursor rules (`.cursor/rules/`)

External Cursor rules are vendored under `.cursor/rules/`. Each file is `.mdc` with YAML frontmatter: `description`, `globs` (and sometimes duplicate `paths`), and `alwaysApply` (when `true`, the rule applies broadly instead of only to glob matches).

A parallel snapshot lives at `.agent/rules/cursor-vendored/` for reference and diffing alongside the main rules tree. Claude Code's rule loader only reads `.md`, so these `.mdc` files cost zero context — they're disk-only documentation. Use the `.md` rules listed above for Claude path-scoped enforcement.
