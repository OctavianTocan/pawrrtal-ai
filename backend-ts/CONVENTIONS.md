# backend-ts conventions

How we lay out Effect TS backend. One section per file role. More sections later.

**Packages**

| Package | Path | Job |
|---------|------|-----|
| Contract | `packages/api-core/` | Schemas, routes, errors. No DB. No server boot. |
| Runtime | `apps/api/` | Handlers, services, repos, auth, `Main.ts` |

Shape like `backend/vendor/comcom`. Effect v4 from `backend/vendor/effect-smol` (`ai-docs/`). Not comcom v3 `@effect/platform` imports.

---

## `Domain.ts` (api-core)

**Job**

Data shapes for one feature: IDs, response entities, create/update bodies. All Effect `Schema`. Same types in `Api.ts`, handlers, services. JSON validate + OpenAPI + typecheck.

**Why "domain"**

DDD name. Business *what data looks like* — not HTTP, not SQL, not workflow. Empty name -> `Untitled Project` lives in `Service.ts` (`apps/api`), not here.

**Path**

```text
packages/api-core/src/Modules/<Feature>/Domain.ts
```

e.g. `Modules/Projects/Domain.ts` = conversation folders (`/api/v1/projects` in Python).

**Put here**

| Kind | Job | Name hint |
|------|-----|-----------|
| ID schema | Identifier type | `ProjectId` |
| Entity | API response object | `Project` |
| Create body | POST payload | `ProjectCreate` |
| Update body | PATCH payload | `ProjectUpdate` |
| Enums | Fixed values | `SessionStatus` |

`Schema.Class` for objects. `.annotations({ description: "..." })` on fields when OpenAPI needs docs (comcom style).

**Not here**

- HTTP method/path/status -> `Api.ts`
- `ProjectNotFoundError` etc -> `Errors.ts`
- SQL -> `Repo.ts` (`apps/api`)
- Auth -> `Policy.ts` (`apps/api`)

**Siblings**

```text
Domain.ts  -> WHAT (Project, ProjectCreate, ProjectId)
Errors.ts  -> fail modes (404, 409)
Api.ts     -> WHERE on wire (GET /, POST /, :id)
```

`Api.ts` pulls types:

```typescript
.addSuccess(Project)
.setPayload(ProjectCreate)
```

`Service.ts` / `Repo.ts` import same types for row -> response mapping.

**Python**

Same as Pydantic in `backend/app/schemas.py` (`ProjectRead`, `ProjectCreate`, `ProjectUpdate`). Strangler: mirror fields in `Domain.ts` first, then `Api.ts`.

---

## `Api.ts` (api-core)

**Job**

HTTP *contract* for one feature: which routes exist, method, path, success type, body, path params, errors. `HttpApiGroup` + `HttpApiEndpoint`. OpenAPI comes from this + `Domain.ts`. **No handler impl** — that is `Http.ts` in `apps/api`.

**Two files named Api.ts**

| File | Job |
|------|-----|
| `Modules/<Feature>/Api.ts` | One route group (`ProjectsApi`, `SystemApi`) |
| `packages/api-core/src/Api.ts` | Root: `.add()` every group, global `/v1` prefix, API title |

**Feature group path**

```text
packages/api-core/src/Modules/<Feature>/Api.ts
```

Export `class ProjectsApi extends HttpApiGroup.make('projects')` (example).

**Group id string**

First arg to `HttpApiGroup.make('projects')` **must match** `HttpApiBuilder.group(Api, 'projects', ...)` in `apps/api/Modules/<Feature>/Http.ts`. Mismatch = handler never wires.

**Typical endpoint chain**

```typescript
HttpApiEndpoint.get('list', '/')
  .addSuccess(Project)           // or array / paginated wrapper
  .addError(ProjectNotFoundError) // from Errors.ts
  .setPath(Schema.Struct({ id: ProjectId }))  // when :id in path
  .setPayload(ProjectCreate)     // POST/PATCH body from Domain.ts
  .annotate(OpenApi.Summary, '...')
```

Methods: `get` | `post` | `patch` | `del`. First string = endpoint name (used in handler map). Second = path **under group prefix**.

**Group-level knobs**

- `.prefix('/projects')` — all endpoints under `/projects` (root `Api` also has `.prefix('/v1')` -> `/v1/projects/...`)
- `.addError(...)` — errors shared by whole group
- `.middleware(...)` — comcom adds auth on group; Pawrrtal may do same later
- `{ topLevel: true }` on group — skip nesting under `/v1` for that group (see `SystemApi` `/health`)

**Root `Api.ts`**

```typescript
export class Api extends HttpApi.make('api')
  .add(SystemApi)
  .add(ProjectsApi)   // each feature group
  .prefix('/v1')
  .annotate(OpenApi.Title, 'Pawrrtal API')
```

New feature: add group here + export from `packages/api-core/src/index.ts`.

**Not here**

- `Effect` that talks to DB -> `Service.ts` / `Repo.ts`
- `HttpApiBuilder.group` handler bodies -> `Http.ts`
- Business rules -> `Service.ts`

**Siblings**

```text
Domain.ts  -> types endpoints reference
Errors.ts  -> .addError(...) targets
Api.ts     -> route table + OpenAPI
Http.ts    -> (apps/api) wire handlers to group id
```

**Python**

Not 1:1 file. Python splits `schemas.py` (Domain) vs `router.py` + `APIRouter` paths (Api). When porting route, read Python router for method/path, schemas for payloads, encode both in `Api.ts`.

**Parity note**

Match Python surface. e.g. projects today: list/create/patch/delete — **no GET by id**. Do not add endpoint in `Api.ts` until product wants it.

---

## Later

- `Errors.ts`
- `Http.ts` (`Http<Feature>Live`)
- `Service.ts`, `Repo.ts`, `Policy.ts`
- `Modules/Layers.ts`
