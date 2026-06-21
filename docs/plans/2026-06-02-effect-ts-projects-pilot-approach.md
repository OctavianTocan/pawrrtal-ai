# Effect TS Projects pilot — approach review

**Date:** 2026-06-02  
**Status:** Draft (research-backed; no implementation in this doc)  
**Scope:** Strangler pilot for `/api/v1/projects` on `backend-ts` (`:8001`) vs Python FastAPI (`:8000`)

---

## Executive summary

The phased plan discussed earlier — **infrastructure → repository → service → HTTP handlers → auth → verification** — is **directionally correct** and matches `backend-ts/CONVENTIONS.md`, the Python projects module, and Effect v4 patterns in `backend/vendor/effect-smol/ai-docs/`.

After reading the repo, vendor docs, and comcom (layout only), the recommendation is **refined**, not replaced:

| Topic | Verdict |
|-------|---------|
| Layer order (DB → Repo → Service → Http) | **Keep** |
| More `api-core` contract work before runtime | **Stop** — contract is sufficient for parity |
| Drizzle (comcom style) for this pilot | **Defer** — use `@effect/sql` already in `apps/api` |
| Auth timing | **Pull earlier than “last”** — required for real parity tests against `:8000` |
| Shared SQLite with Python in dev | **OK for pilot** with documented lock/concurrency caveats |
| `Policy.ts` for Projects | **Optional** — ownership belongs in Repo SQL like Python `crud.py` |
| Frontend / `just dev` cutover | **Later** — after auth, tests, and CI gate on `backend-ts` |

**Do not** add GET-by-id, new endpoints, or conversation-assignment work in this pilot; those are separate surfaces.

---

## 1. What we thought initially

Recommended sequence (three sessions):

1. **Infrastructure** — SQLite `SqlClient` layer, read `DATABASE_URL` / dev DB path (same DB as Python when possible).
2. **ProjectsRepo** — SQL mirroring `backend/app/projects/crud.py`.
3. **ProjectsService** — trim/default name, map missing rows to `ProjectNotFoundError`.
4. **Http.ts** — thin handlers; remove in-memory stubs; wire layers.
5. **Auth** — replace `STUB_USER_ID` with real session user (`get_allowed_user` parity).
6. **Verification** — compare `:8000` vs `:8001`, add first Vitest tests.
7. **Later** — `just dev` runs TS API, CI for `backend-ts`, frontend strangler routing.

That order follows the mental model in `CONVENTIONS.md`: contract (`api-core`) is separate from runtime (`apps/api`), and handlers stay thin.

---

## 2. Current state (codebase)

### Done — contract (`packages/api-core`)

| Artifact | State |
|----------|--------|
| `Modules/Projects/Domain.ts` | Aligned with Python `ProjectRead` / create / update |
| `Modules/Projects/Errors.ts` | `ProjectNotFoundError` (404) on patch/delete |
| `Modules/Projects/Api.ts` | list, create, update, delete — **no GET by id** (matches Python router) |
| `Api.ts` | `ProjectsApi` under `/api/v1` |

### Done — shell (`apps/api`)

| Artifact | State |
|----------|--------|
| `Main.ts` | Server on port **8001** |
| `App.ts` | `HttpApiBuilder.layer` + Scalar `/docs` |
| `Modules/System/Http.ts` | Health (reference for thin handler) |
| `Modules/Layers.ts` | Merges HTTP lives only — **no DB/service layers yet** |

### Not done — runtime

| Artifact | State |
|----------|--------|
| `Infrastructure/` | **Missing** (mentioned in `AGENTS.md`, not created) |
| `Modules/Projects/Repo.ts` | **Interface only** — no `Layer` implementation |
| `Modules/Projects/Service.ts` | **Empty** `Context.Service` |
| `Modules/Projects/Http.ts` | **Stubs** — fake projects, always-success update/delete |
| Auth | `STUB_USER_ID` constant |
| Tests / CI | No `backend-ts` tests; no dedicated CI workflow; not started by `just dev` |

### Python parity target

- Router: `backend/app/projects/router.py` — `get_allowed_user`, `get_async_session`, 404 on failed update/delete.
- CRUD: `backend/app/projects/crud.py` — user-scoped queries, oldest-first list, create trim → `"Untitled Project"`, update only mutates non-empty trimmed name.
- Model: `projects` table — `id`, `user_id`, `name`, `created_at`, `updated_at`; FK from conversations `ON DELETE SET NULL`.

### Product context (out of pilot scope)

- Frontend projects UI and conversation `project_id` assignment ship against **Python `:8000`** (`frontend/lib/api.ts`).
- Pilot success = **behavioral parity on the four project routes**, not moving the UI to `:8001`.

---

## 3. Research — what confirms the plan

### 3.1 Effect v4 HTTP wiring

`backend/vendor/effect-smol/ai-docs/src/51_http-server/10_basics.ts` shows the intended shape:

- `HttpApiBuilder.layer(Api)` provides routes.
- Handler modules are separate `HttpApiBuilder.group` layers.
- Composition via `Layer.provide([...handlerLayers])` on the API layer.

Pawrrtal already mirrors this in `App.ts` (`Layer.provide(CoreModulesLive)`). Next step is providing **Repo + Service (+ Sql)** into `HttpProjectsLive`, same as comcom provides `UserSettings.Default` on `HttpUserSettingsLive`.

### 3.2 `Context.Service` in Pawrrtal

Pawrrtal uses Effect v4 `Context.Service` for `ProjectsRepo` / `ProjectsService` and in the authorization fixture (`fixtures/api/Authorization.ts`). That matches the pinned stack (`4.0.0-beta.74`), not comcom’s Effect v3 `Effect.Service` + `.Default`.

### 3.3 SQL package choice

`apps/api/package.json` already depends on `@effect/sql-sqlite-node`. Vendor implementation (`packages/sql/sqlite-node/src/SqliteClient.ts`) documents:

- `SqliteClient.layer` / `layerConfig` for file-backed DB.
- Exposes generic `SqlClient` for tagged SQL.

`CONVENTIONS.md` explicitly says: read `effect-smol` `ai-docs/`, do **not** copy comcom’s `@effect/platform` / v3 imports.

### 3.4 Comcom as layout reference only

`backend/vendor/comcom/apps/api/src/Modules/UserSettings/` demonstrates the **roles** we want:

- **Http** — `yield* UserSettings`, `requirePolicy`, pipe helpers.
- **Service** — orchestration.
- **Repo** — Drizzle queries.
- **Infrastructure/Database** — shared DB layer.

Comcom uses **Postgres + Drizzle** (`Infrastructure/Database/Drizzle.ts`). Pawrrtal dev often uses **SQLite** (`pawrrtal.db`); production may use Postgres (`backend/.env.example`). For the pilot, **Effect SQL with a swappable client layer** is enough; duplicating Drizzle schemas in TS is extra scope.

### 3.5 Contract completeness

`ProjectsApi` already encodes status codes (201 create, 204 delete, 404 errors). Further `api-core` edits are only needed when adding **auth middleware** to the group (see §4.2).

---

## 4. Research — what changes the plan

### 4.1 Auth cannot stay last if “parity” means real requests

Stubs today hide two gaps:

- Update/delete **always succeed** (no `ProjectNotFoundError`).
- **No cookie session** — you cannot curl `:8001` with the browser’s `session_token` and compare to `:8000`.

Python auth stack (`backend/app/infrastructure/auth/users.py`):

- Cookie name: `session_token`.
- JWT via `AUTH_SECRET`.
- `get_allowed_user` email allowlist on top of `fastapi_users` current user.

Effect HTTPAPI supports cookies via security middleware, not ad hoc endpoint options:

- `HttpApiSecurity.apiKey({ in: "cookie", key: "session" })` (see `backend/vendor/effect-smol/packages/effect/HTTPAPI.md` and platform-node tests).
- Fixture `Authorization.ts` uses **bearer** — useful sample, **wrong transport for Pawrrtal**.

**Revised placement:** implement **auth middleware after Service + Http are wired**, but **before** calling the pilot “done” or routing any real client. For automated tests, provide a test `CurrentUser` layer without going through JWT.

### 4.2 Repo interface should scope by `user_id` on mutations

Current `ProjectsRepo` (`apps/api/src/Modules/Projects/Repo.ts`):

- `update(id, input)` and `delete(id)` **omit `userId`**.

Python always scopes by `user_id` in SQL. Service should not be the only place enforcing ownership — Repo methods should match `crud.get_project` / `update_project` / `delete_project` signatures.

**Action when implementing:** add `userId` to update/delete (or pass ownership context object) so SQL uses `WHERE id = ? AND user_id = ?`.

### 4.3 Shared SQLite: workable, not invisible

- Python: `sqlite+aiosqlite` async driver.
- Effect Node: `better-sqlite3` — **synchronous**, serialized per client (vendor docs).

Both processes opening the same `pawrrtal.db` in dev can see **lock contention** under concurrent writes. Acceptable for local strangler work; document “don’t hammer both APIs with parallel writes” and expect Postgres in production with `@effect/sql-pg` later.

**Do not** give TS a separate empty DB if the goal is parity with existing projects created via Python.

### 4.4 `Policy.ts` is optional for this slice

Comcom uses `Policy.ts` + `requirePolicy` for capability checks. Projects today only need **“same user owns row”**, which Python implements in CRUD, not a separate policy module.

Add `Policy.ts` when routes need roles beyond ownership (or shared RLS helpers like comcom’s `requireRls`). Not required for pilot completion.

### 4.5 Verification and CI gaps

| Gap | Risk |
|-----|------|
| No Vitest tests in `backend-ts` | Regressions on 404, ordering, name trim |
| No CI job for `just typecheck-backend-ts` | Drift merges unnoticed |
| TS API not in `just dev` | Easy to forget to run `:8001` |

**Minimum bar before frontend cutover:** scoped HTTP tests (or integration tests with test DB) + CI typecheck; manual cookie parity checklist against `:8000`.

### 4.6 Stub handler bugs to fix when wiring Http

Current stub `update` returns a synthetic project even when id does not exist; `delete` is always void. Service must:

- `update` → `Option.none` / null from Repo → `Effect.fail(new ProjectNotFoundError(...))`.
- `delete` → `false` from Repo → same 404.

---

## 5. Revised recommended sequence

### Phase A — Runtime foundation (session 1)

1. **`Infrastructure/Database/`** (or `Infrastructure/Sql/`)
   - `SqliteClient.layerConfig` (or equivalent) reading env aligned with Python (`DATABASE_URL` / sqlite filename from `backend/app/infrastructure/config.py` behavior).
   - Export `DatabaseLive` merging `SqlClient` (+ optional `SqliteClient` if needed).
2. **`ProjectsRepo` implementation**
   - Tagged SQL; table `projects`; map to `Project` schema (`DateTime` fields).
   - Parity: list `ORDER BY created_at ASC`, create with trim/default name, user-scoped update/delete.
   - **Fix interface** to pass `userId` on mutations.
3. **`ProjectsRepoLive` layer** — `Layer.effect` / scoped layer pattern consistent with other v4 services in repo.

### Phase B — Business + HTTP (session 2)

4. **`ProjectsService`**
   - Delegate to Repo; encode trim/default rules; fail with `ProjectNotFoundError`.
5. **`HttpProjectsLive`**
   - Thin handlers calling Service.
   - `HttpProjectsLive.pipe(Layer.provide(ProjectsServiceLive), Layer.provide(ProjectsRepoLive), Layer.provide(DatabaseLive))`.
   - Remove stubs and `stubProject`.
6. **Wire `CoreModulesLive` / `App.ts`** if any global layer ordering is needed (usually per-handler `provide` is enough).

### Phase C — Auth + proof (session 3)

7. **Auth middleware** (api-core definition + apps/api implementation)
   - Cookie `session_token`, JWT validation with `AUTH_SECRET`.
   - `CurrentUser` service with `UserId` (and email for allowlist).
   - Attach middleware on `ProjectsApi` (and later other groups).
8. **Parity verification**
   - Same user cookie → create/list/update/delete on `:8000` and `:8001`; compare bodies and status codes.
   - Edge cases: empty name → Untitled; whitespace-only update preserves name; wrong id → 404; another user’s id → 404.
9. **Tests + CI**
   - Vitest: Service unit tests + optional HTTP test with mocked `CurrentUser`.
   - Add CI workflow step: `just typecheck-backend-ts` (actor-gated self-hosted per repo rules).

### Phase D — Strangler operations (later)

10. Optional `just dev` flag to start `:8001`.
11. Frontend env / proxy to hit TS for projects only.
12. Postgres client layer for production Railway (if not already on Postgres).

---

## 6. What not to do (yet)

| Temptation | Why defer |
|------------|-----------|
| Port Drizzle + shared schema package | Duplication vs Python SQLAlchemy; `@effect/sql` is enough for four queries |
| Copy comcom imports (`@effect/platform`, v3) | Wrong Effect major version |
| Add GET `/projects/:id` | Not in Python router; expand only with product need |
| Implement conversation `project_id` PATCH | Different route; frontend already on Python |
| Bearer-only auth from effect fixture | Pawrrtal uses session cookies |
| More `api-core` schema churn | Contract matches Python; invest in runtime |
| Frontend switch before auth + tests | Hides stub bugs and auth gaps |

---

## 7. Open questions (decide before production strangler)

1. **Postgres timing:** implement `SqlClient` abstraction now with SQLite only, or add `@effect/sql-pg` in the same PR series?
2. **Allowlist:** replicate `get_allowed_user` exactly in TS middleware, or shared auth service later?
3. **Migrations:** TS reads Alembic-managed schema only (recommended) — confirm no TS-owned migrations for `projects`.
4. **Error body shape:** match Python `detail: "Project not found"` string vs structured `ProjectNotFoundError` JSON — check frontend expectations (likely only status code matters today).

---

## 8. Conclusion

**Yes — the original bottom-up plan is the right way to go**, with these important adjustments:

1. Treat **api-core as complete** for the pilot; focus on `apps/api` runtime.
2. Use **`@effect/sql-sqlite-node`**, not Drizzle-from-comcom, for the first Repo.
3. **Scope Repo mutations by `user_id`** like Python.
4. Plan **cookie/JWT auth before declaring parity**, not as an optional follow-up.
5. Add **tests + CI** before any frontend routing change.
6. Document **SQLite dual-process** limitations in dev.

That sequence teaches the Pawrrtal Effect stack (layers, middleware, SQL, errors) on the smallest real vertical slice without expanding product scope.

---

## References

| Resource | Path |
|----------|------|
| Pawrrtal TS conventions | `backend-ts/CONVENTIONS.md` |
| Pawrrtal TS README | `backend-ts/README.md` |
| Effect HTTP basics | `backend/vendor/effect-smol/ai-docs/src/51_http-server/10_basics.ts` |
| Effect auth fixture | `backend/vendor/effect-smol/ai-docs/src/51_http-server/fixtures/api/Authorization.ts` |
| Effect SQL SQLite Node | `backend/vendor/effect-smol/packages/sql/sqlite-node/src/SqliteClient.ts` |
| HTTPAPI cookies doc | `backend/vendor/effect-smol/packages/effect/HTTPAPI.md` |
| Comcom UserSettings pattern | `backend/vendor/comcom/apps/api/src/Modules/UserSettings/` |
| Python projects router | `backend/app/projects/router.py` |
| Python projects CRUD | `backend/app/projects/crud.py` |
| Python auth | `backend/app/infrastructure/auth/users.py` |
