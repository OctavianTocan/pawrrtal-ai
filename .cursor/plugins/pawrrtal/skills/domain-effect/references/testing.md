# Testing

Use this when adding tests under `backend-ts/apps/api/test/`, designing
Repo/Service/Http test layers, choosing test doubles, or refactoring a service
to be testable.

## Where Tests Live

```text
backend-ts/apps/api/
├── src/
└── test/
    ├── unit/
    │   ├── _helpers/
    │   ├── _shared/
    │   ├── Infrastructure/
    │   └── Modules/<Name>/
    │       ├── Repo.test.ts
    │       ├── Service.test.ts
    │       └── Http.test.ts
    └── integration/
```

- `unit/` holds fast unit and integration-style tests.
- Mirror `src/` paths so reviewers can navigate by feature.
- Underscore-prefixed helpers are shared infrastructure, not feature coverage.
- Test files are exempt from nesting checks but not from the 500-line file cap.

## Service Contract

Every `Effect.Service` used by app modules should produce the standard pair:

| Layer | What It Is | Used By |
| --- | --- | --- |
| `Foo.Default` | service body plus production dependencies | runtime |
| `Foo.DefaultWithoutDependencies` | service body without dependencies | tests with overrides |

Do not invent custom `_Unprovided` exports. Use
`DefaultWithoutDependencies` when a test needs to provide a mock repo, fake auth,
or in-memory database.

## Repo Tests

Prefer an in-memory SQLite database when SQL behavior is non-trivial. Check
`backend/vendor/effect-smol/packages/sql/sqlite-node/test/Resolver.test.ts`
for the current v4 beta pattern before copying API calls.

`better-sqlite3` rejects `Date` for `TEXT` columns. Convert at the boundary:

```ts
const ts = DateTime.formatIso(now)
```

## Service Tests

Use a `Ref`-backed stub for repo dependencies when testing business mapping.
Exercise the real service body through `DefaultWithoutDependencies`; do not
inline the service implementation in the test.

Avoid `Effect.sleep` in test bodies because the test runtime uses `TestClock`.
Stub a clock/time service when order matters.

## HTTP Tests

Do not bind a real port. Use `HttpApiBuilder.toWebHandler` to get a
`fetch`-compatible handler and call it with `Request` objects.

For coverage that exercises the real handler plus service plus repo, assemble
the production handler/service with an in-memory database layer, then call the
same web handler.

## Gates

```bash
cd backend-ts && bun run typecheck
cd backend-ts && bun run test
```
