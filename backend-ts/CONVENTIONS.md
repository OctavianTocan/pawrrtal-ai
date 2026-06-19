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

## Decode boundaries (`Schema.Class`)

How to turn **external data** (HTTP JSON, SQL rows) into **`Schema.Class` domain instances** without fighting Effect v4 types.

**Read first**

| Reference | Path | What it shows |
|-----------|------|---------------|
| Effect v4 HttpClient walkthrough | `backend/vendor/effect-smol/ai-docs/src/50_http-client/10_basics.ts` | `Context.Service` + `Layer.effect`, client middleware, `HttpClientResponse.schemaBodyJson` |
| Effect HttpClient tests | `backend/vendor/effect-smol/packages/effect/test/HttpClient.test.ts` | `Schema.Struct` fixture + `schemaBodyJson`; request encoding via `HttpClientRequest.schemaBodyJson` (prefer over `bodyJsonUnsafe`) |
| `schemaBodyJson` typing | `backend/vendor/effect-smol/packages/effect/src/unstable/http/HttpIncomingMessage.ts` | Returns `Effect<S["Type"], …, S["DecodingServices"]>` |
| comcom external REST client | `backend/vendor/comcom/packages/clients/autumn/src/Client.ts` | v3 `schemaBodyJson(Schema.Class)` + shared `decodeWith` helper |
| comcom OAuth wire decode | `backend/vendor/comcom/apps/api/src/Modules/Integrations/Engine/OAuthHttp.ts` | `Schema.Struct` wire schema + `Schema.decodeUnknown` |
| comcom DB → Class | `backend/vendor/comcom/apps/api/src/Modules/Acl/Service.ts` | `new AclEntry(row)` from repo row |
| Pawrrtal DB → Class | `backend-ts/apps/api/src/Modules/Projects/Repo.ts` | `new Project({…})` + comment on v4 `DecodingServices` |
| Pawrrtal HttpClient service shell | `backend-ts/apps/api/src/Modules/Auth/SessionStore.ts` | `Context.Service` + `Body`/`Live` split, Python strangler client |
| Vendor roles | `backend/vendor/README.md` | effect-smol = v4 source of truth; comcom = layout only (no v3 imports) |

**Rule of thumb:** domain entities are always `Schema.Class` in `Domain.ts`. *How* you decode depends on **where the bytes come from**, not on the entity type.

### Decision tree

```text
Where does the data come from?
│
├─ DB row / trusted internal driver output
│   └─ new DomainClass({ …from row… })          ← Repo pattern
│
├─ External HTTP JSON (same shape as domain Class)
│   ├─ schemaBodyJson(DomainClass) type-checks with R = never
│   │   └─ use it directly                      ← ai-docs / Autumn pattern
│   └─ schemaBodyJson(DomainClass) leaks unknown into R  (Pawrrtal v4 quirk)
│       └─ schemaBodyJson(Struct(Class.fields))
│           then new DomainClass(data)          ← hybrid; SessionStore target shape
│
└─ External HTTP JSON (wire-only / different shape)
    └─ Schema.Struct in Domain or client module
        + schemaBodyJson or decodeUnknown       ← comcom OAuth pattern
```

Do **not** add a separate wire schema when JSON shape is identical to the domain Class — derive from `Class.fields` instead.

### Pattern 1 — DB / trusted boundary (`Repo.ts`)

Use when SQL (or another trusted driver) returns a row you control.

```typescript
const decodeProject = (row: Record<string, unknown>): Project =>
  new Project({
    id: row.id as ProjectId,
    user_id: row.user_id as UserId,
    name: row.name as string,
    created_at: DateTime.makeUnsafe(row.created_at as string),
    updated_at: DateTime.makeUnsafe(row.updated_at as string),
  });
```

**Why not `Schema.decodeUnknownSync(Project)(row)`:** `Schema.Class` surfaces `DecodingServices = unknown` in v4, so sync decode needs an R-channel and does not fit a sync repo helper. Direct construction is the idiomatic Pawrrtal v4 pattern.

**Reference:** `backend-ts/apps/api/src/Modules/Projects/Repo.ts` (lines 7–19, 20–27).

### Pattern 2 — External HttpClient, Class decode works (`schemaBodyJson(Class)`)

Use when calling an external REST API and `schemaBodyJson(DomainClass)` type-checks with **`R = never`** on your service method.

**Service shell** (Pawrrtal v4 — translates comcom `Effect.Service` + `.Default`):

```typescript
export class MyClient extends Context.Service<
  MyClient,
  { readonly fetch: (id: string) => Effect.Effect<Thing, MyClientError> }
>()('@apps/api/MyClient') {}

export const MyClientBody: Layer.Layer<MyClient, never, HttpClient.HttpClient> =
  Layer.effect(MyClient, Effect.gen(function* () {
    const client = (yield* HttpClient.HttpClient).pipe(
      HttpClient.mapRequest(flow(
        HttpClientRequest.prependUrl('https://api.example.com'),
        HttpClientRequest.acceptJson,
      )),
      HttpClient.filterStatusOk,
      HttpClient.retryTransient({ schedule: Schedule.exponential(100), times: 3 }),
    );

    const fetch = Effect.fn('MyClient.fetch')(function* (id: string) {
      return yield* client.get(`/things/${id}`).pipe(
        Effect.flatMap(HttpClientResponse.schemaBodyJson(Thing)),
        Effect.mapError((cause) => new MyClientError({ cause })),
        Effect.withSpan('MyClient.fetch'),
      );
    });

    return MyClient.of({ fetch });
  }));

export const MyClientLive: Layer.Layer<MyClient, never, never> =
  Layer.provide(MyClientBody, [FetchHttpClient.layer]);
```

**Reference:** `backend/vendor/effect-smol/ai-docs/src/50_http-client/10_basics.ts` (full file); comcom `decodeWith` in `backend/vendor/comcom/packages/clients/autumn/src/Client.ts` (lines 185–218, 235–242).

**Request bodies** (POST/PATCH to external APIs): derive payload schema from Class fields, encode with `HttpClientRequest.schemaBodyJson`:

```typescript
const ThingCreate = Schema.Struct(Struct.omit(Thing.fields, ['id']));
// …
HttpClientRequest.post('/things').pipe(
  HttpClientRequest.schemaBodyJson(ThingCreate)(body),
  client.execute,
  Effect.flatMap(HttpClientResponse.schemaBodyJson(Thing)),
);
```

**Reference:** `backend/vendor/effect-smol/packages/effect/test/HttpClient.test.ts` (lines 6–14, 21–25).

### Pattern 3 — External HttpClient, Class decode blocks typing (hybrid)

Use when `schemaBodyJson(DomainClass)` puts **`unknown`** in the Effect R-channel but your service contract requires **`Effect<A, E, never>`** (implicit on `Effect.Effect<A, E>`).

Typical for Pawrrtal domain Classes with refined fields (`UserId`, email pattern checks, etc.).

```typescript
import { Schema } from 'effect';
import { User } from '@pawrrtal/api-core/Modules/Auth/Domain';

const UserWire = Schema.Struct(User.fields);

// inside lookup / fetch:
yield* client.get('users/me', { headers: { Cookie: `session_token=${token}` } }).pipe(
  Effect.flatMap(HttpClientResponse.schemaBodyJson(UserWire)),
  Effect.map((data) => new User(data)),
  Effect.mapError((cause) => new SessionStoreError({ message: 'Failed to lookup user', cause })),
  Effect.withSpan('SessionStore.lookup'),
);
```

- **`UserWire`** — wire decode; `DecodingServices` stays `never` on Struct.
- **`new User(data)`** — validated class instance (constructor runs schema checks).
- Keeps effect-smol's `schemaBodyJson` on the HTTP step; avoids manual `response.json` + field casts.

**Apply to:** `backend-ts/apps/api/src/Modules/Auth/SessionStore.ts` when you refactor lookup.

**Why the ai-docs example uses `schemaBodyJson(Todo)` directly:** ai-docs `Todo` has only primitive fields; it may type-check cleanly. Pawrrtal `User` with branded IDs and checks hit the v4 Class R-channel issue — the hybrid is the Pawrrtal-specific fix, not a rejection of ai-docs.

### Pattern 4 — Wire-only integration (`Schema.Struct`)

Use when JSON shape is **not** a domain entity (OAuth tokens, vendor-specific payloads).

```typescript
const TokenSuccess = Schema.Struct({
  access_token: Schema.String,
  refresh_token: Schema.optional(Schema.String),
  expires_in: Schema.optional(Schema.Union(Schema.Number, Schema.NumberFromString)),
});

const decodeSuccess = Schema.decodeUnknown(TokenSuccess);
// … yield* decodeSuccess(parsedBody).pipe(Effect.mapError(...))
```

Put the Struct in `Domain.ts` if shared across modules; keep local to the client file if one-off.

**Reference:** `backend/vendor/comcom/apps/api/src/Modules/Integrations/Engine/OAuthHttp.ts` (lines 90–105, 116–117, 299–308).

### What not to do

| Don't | Do instead |
|-------|------------|
| Copy comcom `@effect/platform` imports | `effect/unstable/http` per `backend/vendor/README.md` |
| `Schema.decodeUnknownSync(DomainClass)` in repos | `new DomainClass({…})` (Pattern 1) |
| `bodyJsonUnsafe` for external request bodies | `HttpClientRequest.schemaBodyJson` (see HttpClient.test.ts) |
| Parallel wire + domain schemas when shapes match | `Schema.Struct(DomainClass.fields)` (Pattern 3) |
| Skip decode validation on untrusted HTTP | Always `schemaBodyJson` or `decodeUnknown` on wire Struct |

### Quick reference — boundary → mechanism

| Boundary | Mechanism | Produces |
|----------|-----------|----------|
| SQL row | `new Project(row)` | `Schema.Class` instance |
| External HTTP (Class types clean) | `schemaBodyJson(DomainClass)` | `Schema.Class` instance |
| External HTTP (Class R blocked) | `schemaBodyJson(Struct(Class.fields))` → `new Class` | `Schema.Class` instance |
| OAuth / vendor wire | `Schema.Struct` + `schemaBodyJson` or `decodeUnknown` | Struct `Type` (plain object) |

---

## Later

- `Errors.ts`
- `Http.ts` (`Http<Feature>Live`)
- `Service.ts`, `Repo.ts`, `Policy.ts`
- `Modules/Layers.ts`
