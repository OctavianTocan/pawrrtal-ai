---
# pawrrtal-46yb
title: backend-ts Projects pilot — Service/Repo/Http tests
status: todo
type: feature
priority: high
tags:
    - backend-ts
    - effect-v4
    - pilot
created_at: 2026-06-08T12:36:01Z
updated_at: 2026-06-08T12:36:01Z
---

## Goal

Ship the first automated test coverage for the Effect TS Projects pilot so we can prove the
Service / Repo / Http layers match Python behavior before the pilot is called done.

## Why now

`apps/api/src/Modules/Projects/{Http,Repo,Service}.ts` are wired and typecheck but have **zero
automated coverage**. Phase C-1 (auth middleware) and slice 2/3 of this work all lean on the
Service/Repo contract being correct; without tests, regressions on 404 mapping, name trim,
user-scoped SQL, or wire status codes ship silently. Plan §4.6 calls out the stub handler
bugs we already fixed — tests are how we keep them fixed.

## File

- `backend-ts/package.json` — add `test` script and `@effect/vitest` + `vitest` devDeps
- `backend-ts/apps/api/package.json` — add `@effect/vitest` + `vitest` devDeps (so the test
  files in `apps/api/test/` resolve them)
- `backend-ts/vitest.config.ts` — root config (new)
- `backend-ts/vitest.shared.ts` — shared Vite config (new)
- `backend-ts/apps/api/vitest.config.ts` — package config (new)
- `backend-ts/apps/api/test/fixtures/in-memory-db.ts` — `SqliteClient.make({ filename: ":memory:" })` + `CREATE TABLE projects` (new)
- `backend-ts/apps/api/test/fixtures/current-user-test.ts` — test-only `CurrentUser` Context.Service + `CurrentUserTest` layer (new, fixture only — does **not** change `Http.ts` which keeps `STUB_USER_ID` until Phase C-1)
- `backend-ts/apps/api/test/fixtures/http-client.ts` — `HttpApiClient.make(Api, ...)` wired to handler layers (new)
- `backend-ts/apps/api/test/Modules/Projects/Service.test.ts` — service unit tests (new)
- `backend-ts/apps/api/test/Modules/Projects/Repo.test.ts` — SQL integration tests (new)
- `backend-ts/apps/api/test/Modules/Projects/Http.test.ts` — HTTP integration tests (new)

## Steps

### 1. Wire vitest

1. Add to `backend-ts/package.json`:
   ```jsonc
   "scripts": {
     "install:deps": "bun install",
     "typecheck": "bun run --filter '@pawrrtal/*' typecheck",
     "test": "vitest run --passWithNoTests"
   },
   "devDependencies": {
     "@effect/language-service": "^0.85.1",
     "@effect/vitest": "4.0.0-beta.74",
     "@types/bun": "latest",
     "typescript": "^5.9.3",
     "vitest": "^3.0.0"
   }
   ```
2. Add to `backend-ts/apps/api/package.json`:
   ```jsonc
   "devDependencies": {
     "@effect/vitest": "4.0.0-beta.74",
     "@types/bun": "latest",
     "typescript": "^5.9.3",
     "vitest": "^3.0.0"
   }
   ```
3. Create `backend-ts/vitest.config.ts`:
   ```typescript
   import { mergeConfig } from "vitest/config";
   import shared from "./vitest.shared";

   export default mergeConfig(shared, {
     test: {
       include: ["**/test/**/*.test.ts"],
       exclude: ["**/node_modules/**", "**/dist/**", "**/.next/**"],
       globals: false,
       testTimeout: 30_000,
     },
   });
   ```
4. Create `backend-ts/vitest.shared.ts`:
   ```typescript
   import type { ViteUserConfig } from "vitest/config";

   const config: ViteUserConfig = {
     esbuild: { target: "es2020" },
     optimizeDeps: { exclude: ["bun:sqlite"] },
   };

   export default config;
   ```
5. Create `backend-ts/apps/api/vitest.config.ts` (empty merge to inherit root):
   ```typescript
   import { mergeConfig } from "vitest/config";
   import shared from "../../vitest.shared";

   export default mergeConfig(shared, {});
   ```
6. `cd backend-ts && bun install` to refresh lockfile.

### 2. Add the test fixtures

`backend-ts/apps/api/test/fixtures/in-memory-db.ts`:
```typescript
import { SqliteClient } from "@effect/sql-sqlite-node";
import { Effect, Layer } from "effect";
import { SqlClient } from "effect/unstable/sql";
import { Reactivity } from "effect/unstable/reactivity";

/** Build a fresh, schema-loaded :memory: DB layer per test suite. */
export const makeInMemoryDatabase = ():
  Layer.Layer<SqliteClient.SqliteClient | SqlClient.SqlClient> =>
  Effect.gen(function* () {
    const client = yield* SqliteClient.make({ filename: ":memory:" });
    // Mirror backend/app/models.py → projects table.
    yield* client`CREATE TABLE projects (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      name TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )`;
    return client;
  }).pipe(Layer.unwrap, Layer.provide(Reactivity.layer));
```

`backend-ts/apps/api/test/fixtures/current-user-test.ts`:
```typescript
import { Context, Layer } from "effect";
import type { UserId } from "@pawrrtal/api-core/Modules/Projects/Domain";

/**
 * Test-only CurrentUser service. Matches the shape Phase C-1's auth
 * middleware will provide. Do NOT import this from Http.ts yet — Http
 * keeps STUB_USER_ID until cookie auth lands. Replace the import path
 * here when the real CurrentUser lands in apps/api/src/Modules/Auth.
 */
export class CurrentUser extends Context.Service<CurrentUser, { readonly userId: UserId }>()(
  "@pawrrtal/api/Auth/CurrentUser"
) {}

export const CurrentUserTest = (
  userId: UserId = "00000000-0000-0000-0000-000000000001" as UserId
) => Layer.succeed(CurrentUser, { userId });
```

`backend-ts/apps/api/test/fixtures/http-client.ts`:
```typescript
import { Api } from "@pawrrtal/api-core";
import { Layer } from "effect";
import { FetchHttpClient, HttpClient, HttpClientRequest } from "effect/unstable/http";
import { HttpApiClient } from "effect/unstable/httpapi";
import { DatabaseLive } from "@/Infrastructure/Database";
import { HttpProjectsLive } from "@/Modules/Projects/Http";
import { ProjectsRepoLive } from "@/Modules/Projects/Repo";
import { ProjectsServiceLive } from "@/Modules/Projects/Service";

/**
 * Build a typed HttpApiClient against the wired handler stack. No real
 * server, no port — the client drives handlers through the Effect
 * runtime. Pattern: backend/vendor/effect-smol/ai-docs/src/51_http-server/
 * 10_basics.ts:108 (HttpApiClient.make + transformClient).
 */
export const makeTestApi = () =>
  HttpApiClient.make(Api, {
    transformClient: (client) =>
      client.pipe(
        HttpClient.mapRequest(
          HttpClientRequest.prependUrl("http://test.invalid")
        ),
        HttpClient.retryTransient({ times: 0 })
      ),
  }).pipe(
    Layer.provide([
      FetchHttpClient.layer,
      HttpProjectsLive,
      DatabaseLive,
      ProjectsRepoLive,
      ProjectsServiceLive,
    ])
  );
```

### 3. Service unit tests

`backend-ts/apps/api/test/Modules/Projects/Service.test.ts` — mirrors
`backend/tests/test_project_crud.py:1-169`. Use a `ProjectsRepoTest` layer that reads/writes
a `Ref<ReadonlyArray<Project>>` (pattern from `ai-docs/src/09_testing/20_layer-tests.ts:97`).

Test cases (each is one `it.effect`):

| # | Test | Asserts |
|---|------|---------|
| 1 | `create` with `"   "` | stored as `"Untitled Project"` |
| 2 | `create` with `"  real  "` | stored as `"real"` (trim) |
| 3 | `create` then `list` | length 1, `created_at` ascending |
| 4 | `list` isolation | only rows with matching `userId` |
| 5 | `update` with `name: null` | keeps existing name |
| 6 | `update` with `name: "  "` | keeps existing name (no Untitled rename) |
| 7 | `update` with `name: "new"` | rewrites; `updated_at` strictly greater |
| 8 | `update` on foreign project | `Effect.fail(ProjectNotFoundError)` |
| 9 | `update` on missing id | `Effect.fail(ProjectNotFoundError)` |
| 10 | `delete` on existing | `void`; subsequent `list` excludes it |
| 11 | `delete` on missing | `Effect.fail(ProjectNotFoundError)` |

### 4. Repo integration tests

`backend-ts/apps/api/test/Modules/Projects/Repo.test.ts` — uses `makeInMemoryDatabase()` +
`layer(ProjectsRepoLive)` from `@effect/vitest`. Catches SQL regressions unit tests miss.

Test cases:

| # | Test | Asserts |
|---|------|---------|
| 1 | `listByUser` user-scoped | other user's projects excluded |
| 2 | `listByUser` ordering | `created_at ASC` |
| 3 | `insert` round-trip | all 5 fields persisted; `DateTime` parseable |
| 4 | `update` with mismatched `userId` | returns `null` (Repo, not Service) |
| 5 | `update` with matching `userId` | returns updated row |
| 6 | `delete` with mismatched `userId` | returns `false` |
| 7 | `delete` with matching `userId` | returns `true`; row gone |

### 5. HTTP integration tests

`backend-ts/apps/api/test/Modules/Projects/Http.test.ts` — uses `makeTestApi()`. Note:
the test client still uses the `STUB_USER_ID` inside `Http.ts:12` because we are NOT
introducing real auth in this slice. Tests assert the wire surface and 404 mapping.

Test cases:

| # | Test | Asserts |
|---|------|---------|
| 1 | `POST /` (create) | 201, body matches `Project` schema |
| 2 | `GET /` (list) | 200, array length matches create count |
| 3 | `PATCH /:id` (update) | 200, name updated |
| 4 | `PATCH /:unknown` | 404, `ProjectNotFoundError` |
| 5 | `DELETE /:id` | 204 |
| 6 | `DELETE /:unknown` | 404, `ProjectNotFoundError` |

### 6. Local gate (run before committing)

```bash
cd backend-ts && bun run test
cd backend-ts && bun run typecheck
just check
```

All three must be green. `scripts/check-file-lines.mjs` already scans `backend-ts/**`;
`scripts/check-nesting.mjs` exempts `*.test.ts`.

## Rules

- **Do not** modify `Http.ts`, `Service.ts`, or `Repo.ts` for the sake of tests. The
  `STUB_USER_ID` constant at `Http.ts:12` stays until Phase C-1 (cookie auth).
- **Do not** vendor `better-sqlite3`; rely on the `apps/api` dep already declared.
- **Do not** add a coverage threshold — match the frontend's pattern of uploading v8
  reports without gating.
- Test files stay under 500 LOC each (enforced by `scripts/check-file-lines.mjs`).

## Out of scope

- Real `CurrentUser` from JWT/cookie (Phase C-1).
- HTTP tests that exercise user isolation across `STUB_USER_ID` (covered by Repo tests).
- Frontend E2E coverage of `:8001` (slice 3's `just dev` smoke is enough for now).
