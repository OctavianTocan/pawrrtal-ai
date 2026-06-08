---
name: effect-tests-pawrrtal
description: Write Effect TS tests for the backend-ts strangler following Pawrrtal's @comcom-derived conventions. Use when adding tests under `backend-ts/apps/api/test/`, designing Repo/Service/Http test layers, choosing test doubles (mocks vs `:memory:` SQLite), or refactoring a service to be testable.
---

# Effect TS Tests — Pawrrtal Conventions

## Where tests live

```text
backend-ts/
├── apps/api/
│   ├── src/                         # production code
│   └── test/
│       ├── unit/                    # unit + integration tests
│       │   ├── _helpers/            # reusable test infrastructure
│       │   ├── _shared/             # test setup layers (auth, env)
│       │   ├── Infrastructure/      # mirrors src/Infrastructure/
│       │   └── Modules/              # mirrors src/Modules/
│       │       └── Projects/
│       │           ├── Repo.test.ts
│       │           ├── Service.test.ts
│       │           └── Http.test.ts
│       └── integration/             # reserved (empty for pilot)
```

- `unit/` holds everything we have today; the pilot's `:memory:` SQLite
  integration tests live there too — they're fast and offline.
- Mirror `src/` paths so reviewers can navigate by feature.
- Underscore-prefixed (`_helpers`, `_shared`) directories contain
  shared infra and are excluded from any per-feature test counts.
- See `vendor/comcom/apps/api/test/unit/Modules/Secrets/` for the canonical
  shape (`{Repo,Service,Http,Policy,Domain}.test.ts` per module).

## The service contract

Every Effect `Context.Service` or `Effect.Service` in `apps/api/src/` MUST
be written so it produces **two layers**, just like `@comcom` does:

| Layer | What it is | What it provides | Used by |
|---|---|---|---|
| `Foo.Default` / `Foo.DefaultWithoutDependencies` | service body only | `Foo` | tests (with overrides) |
| `FooLive` (e.g. `ProjectsRepoLive`) | `Foo.Default` + production deps | `Foo` + production deps | production wiring |

With `Effect.Service` (v4 beta), this is automatic:

```ts
export class ProjectsRepo extends Effect.Service<ProjectsRepo>()(
  '@pawrrtal/api/Projects/Repo',
  {
    dependencies: [DatabaseLive],   // baked into `Default`
    effect: Effect.gen(function* () {
      const sql = yield* SqlClient.SqlClient;
      // ...methods
    }),
  }
) {}

// Foo.Default → Layer<ProjectsRepo, ..., never>
// Foo.DefaultWithoutDependencies → Layer<ProjectsRepo, ..., SqlClient>
```

Then production wires `ProjectsRepo.Default` (no `Layer.provide` needed at
the call site), and tests wire `ProjectsRepo.DefaultWithoutDependencies.pipe(Layer.provide(myMockLayer))`.

**Do not** invent custom `_Unprovided` exports — `DefaultWithoutDependencies`
is the standard name and the standard pattern.

## Three test files per module

### `Repo.test.ts` — SQL round-trip

Two flavors of "mock" — pick one:

**Real DB (preferred when repo is non-trivial SQL):** `:memory:` SQLite,
build a fresh schema per suite. The vendor pattern is
`backend/vendor/effect-smol/packages/sql/sqlite-node/test/Resolver.test.ts:9-15`
— `Effect.gen` inside `Layer.effectContext` that calls
`SqliteClient.make({ filename: ":memory:" })` and runs `CREATE TABLE`.

```ts
import { SqliteClient } from '@effect/sql-sqlite-node';
import { Context, Effect, Layer, Scope } from 'effect';
import { SqlClient } from 'effect/unstable/sql';
import { Reactivity } from 'effect/unstable/reactivity';

export const makeInMemoryDatabase = (): Layer.Layer<SqliteClient.SqliteClient | SqlClient.SqlClient> =>
  Layer.effectContext(
    Effect.gen(function* () {
      const client = yield* SqliteClient.make({ filename: ':memory:' });
      yield* client`CREATE TABLE projects (...)`;
      yield* Scope.addFinalizer(yield* Effect.scope, Effect.sync(() => client));
      return Context.make(SqliteClient.SqliteClient, client).pipe(
        Context.add(SqlClient.SqlClient, client)
      );
    })
  ).pipe(Layer.provide(Reactivity.layer));
```

**Pure mock (when the SQL is trivial):** a `Ref`-backed stub. Used for
`Service.test.ts`, not `Repo.test.ts` — see below.

**`Date` binding gotcha:** `better-sqlite3` rejects `Date` for `TEXT`
columns. Convert to ISO string at the boundary:

```ts
const ts = DateTime.formatIso(now);  // not DateTime.toDateUtc(now)
```

### `Service.test.ts` — business rules

A `Ref<ReadonlyArray<Project>>`-backed stub of the `Repo` — keeps the
test purely about the Service's mapping logic, no SQL.

```ts
class RepoTestRef extends Context.Service<RepoTestRef, Ref.Ref<readonly Project[]>>()(
  'app/Projects/RepoTestRef'
) {
  static readonly layer = Layer.effect(RepoTestRef, Ref.make<readonly Project[]>([]));
}

const RepoTest = Layer.effect(ProjectsRepo, Effect.gen(function* () {
  const store = yield* RepoTestRef;
  // stub listByUser / insert / update / delete on the Ref
})).pipe(Layer.provideMerge(RepoTestRef.layer));

// layer() builds a shared scope per suite; tests share the Ref (cumulative
// state is fine when each test uses a unique user_id).
layer(ProjectsService.DefaultWithoutDependencies.pipe(
  Layer.provide(RepoTest)
))('ProjectsService', (it) => { it.effect('...', ...) });
```

**Do not** inline the service body in the test — use the real
`DefaultWithoutDependencies` so the test exercises production code.

**No `Effect.sleep` in test bodies** — the test runtime uses `TestClock`
and `sleep` hangs. If you need temporal ordering, manipulate `DateTime` via
a stub service instead.

### `Http.test.ts` — wire surface

**No real port. No real server. No `HttpApiClient`.** Use the vendor's
`HttpApiBuilder.toWebHandler` pattern, which gives you a
`fetch`-compatible `(Request) => Promise<Response>`:

```ts
import { HttpApiBuilder } from 'effect/unstable/httpapi';
import { HttpServer } from 'effect/unstable/http';

const HttpProjectsTestLive = HttpApiBuilder.group(
  Api, 'projects',
  (handlers) => Effect.gen(function* () {
    // yield* deps if any
    return handlers
      .handle('list', () => Effect.succeed([]))
      .handle('create', ({ payload }) => Effect.succeed(fakeProject(payload.name)))
      .handle('update', ({ params, payload }) => Effect.succeed(fakeProject(payload.name ?? 'X', params.project_id)))
      .handle('delete', () => Effect.void);
  })
);

const ApiLive = HttpApiBuilder.api(Api).pipe(
  Layer.provide(HttpProjectsTestLive),
  // ...auth middleware layers, etc.
);

const { handler } = HttpApiBuilder.toWebHandler(
  ApiLive.pipe(Layer.provideMerge(HttpServer.layerContext))
);

// Test:
const response = await handler(new Request('http://localhost/api/v1/projects', {
  method: 'GET', headers: { authorization: 'Bearer test' }
}));
expect(response.status).toBe(200);
```

If you need end-to-end coverage that also exercises the real
Service + Repo (not stubbed at the handler), assemble:

```ts
const ApiLive = HttpApiBuilder.api(Api).pipe(
  Layer.provide(HttpProjectsLive),                 // production handler
  Layer.provide(ProjectsService.Default),          // production service
  Layer.provide(makeInMemoryDatabase())            // test DB
);
```

Use the same `HttpApiBuilder.toWebHandler` to get a `fetch` handler and
call it the same way.

## Lint / format / arch gates

The repo already has these running on `backend-ts/**`:

- `node scripts/check-file-lines.mjs` — 500-line hard ceiling per `.ts` file
- `node scripts/check-nesting.mjs` — depth-3 nesting budget
- `just check` — Biome + the two above

Test files are exempt from the nesting check (the script
`scripts/check-nesting.mjs` has `EXEMPT_SUFFIXES`); they are NOT exempt
from the file-line check. Keep test files under 500 LOC.

## Common pitfalls

| Pitfall | Fix |
|---|---|
| `Ref` data bleeds between tests | Use a unique `userId` per test, not a unique DB |
| `Date` passed to `sql\`\`` for a `TEXT` column | Use `DateTime.formatIso(now)` |
| `Effect.sleep` hangs in tests | Stub a clock service instead of sleeping |
| `HttpApiClient.make(Api, ...)` can't reach a server | Use `HttpApiBuilder.toWebHandler` — no server needed |
| `Layer.provide(ProjectsRepoLive, [...])` doesn't override the inner DB | Use `ProjectsRepo.DefaultWithoutDependencies` — no baked-in deps to race |
| `Layer.unwrap(myEffect)` returns wrong type | Use `Layer.effectContext(myEffect)` instead — runs in scope, returns Context |
