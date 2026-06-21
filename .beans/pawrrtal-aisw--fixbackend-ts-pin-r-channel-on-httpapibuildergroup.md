---
# pawrrtal-aisw
title: 'fix(backend-ts): pin R channel on HttpApiBuilder.group layers to unblock Main.ts'
status: todo
type: bug
priority: normal
tags:
    - backend-ts
    - effect-v4
created_at: 2026-06-06T22:09:53Z
updated_at: 2026-06-06T22:09:53Z
---

## Goal

Make `backend-ts/apps/api/src/Main.ts` typecheck and run. The error
"`Effect<never, never, unknown>` is not assignable to method's `this`
of type `Effect<unknown, unknown, never>`" comes from
`HttpApiBuilder.group` casting its return to `any`
(`@effect-smol/packages/effect/src/unstable/httpapi/HttpApiBuilder.ts:184`).
That widens the resulting `Layer`'s R channel from `never` to `unknown`.
The widening leaks all the way up to `HttpServerLayer`, so
`Layer.launch(HttpServerLayer)` returns `Effect<never, never, unknown>`
— and `NodeRuntime.runMain` (a `dual` whose call signature has implicit
`this: Effect<unknown, unknown, never>`) rejects it on the `.pipe`.

Pin the R channel back to `never` at the boundary by annotating the
two `HttpApiBuilder.group(...)` Layer values with an explicit return
type. Then `Layer.mergeAll`, `HttpApiBuilder.layer`, and `HttpRouter.serve`
all propagate `never` cleanly, and `NodeHttpServer.layer` covers the
single residual group (`Etag | FileSystem | HttpPlatform | Path`).

## Files

- `backend-ts/apps/api/src/Modules/System/Http.ts` — **edit**
- `backend-ts/apps/api/src/Modules/Projects/Http.ts` — **edit**
- `backend-ts/apps/api/src/App.ts` — **verify only**
- `backend-ts/apps/api/src/Main.ts` — **verify only**
- `backend-ts/apps/api/src/Modules/Layers.ts` — **verify only**

## Steps

### 1. Annotate `HttpSystemLive`

**File:** `backend-ts/apps/api/src/Modules/System/Http.ts`

**Why:** `HttpApiBuilder.group` ends with `as any`
(`@effect-smol/packages/effect/src/unstable/httpapi/HttpApiBuilder.ts:184`).
The handlers use no Effect services, so semantically R is `never`; the
`as any` just hides it. Pin the return type so TypeScript tracks it.

Add the `Layer` import. Replace the `const HttpSystemLive = ...` line
(currently line 5) with:

```ts
import { Effect, Layer } from 'effect';
import { HttpApiBuilder } from 'effect/unstable/httpapi';
import { Api } from '@pawrrtal/api-core';

export const HttpSystemLive: Layer.Layer<never, never, never> = HttpApiBuilder.group(
	Api,
	'system',
	Effect.fn(function* (handlers) {
		return handlers.handle('health', () => Effect.void);
	})
);
```

### 2. Annotate `HttpProjectsLive`

**File:** `backend-ts/apps/api/src/Modules/Projects/Http.ts`

Same `as any` widening happens here. Add `import { Layer } from 'effect';`
and replace the `export const HttpProjectsLive = ...` line (currently
line 27) with:

```ts
export const HttpProjectsLive: Layer.Layer<never, never, never> = HttpApiBuilder.group(
	Api,
	'projects',
	Effect.fn(function* (handlers) {
		return handlers
			.handle('list', () => Effect.succeed([]))
			.handle('create', ({ payload }) =>
				Effect.succeed(
					stubProject(
						payload.name.trim() || 'Untitled Project',
						crypto.randomUUID() as ProjectId
					)
				)
			)
			.handle('update', ({ params, payload }) =>
				Effect.succeed(
					stubProject(payload.name?.trim() || 'Untitled Project', params.project_id)
				)
			)
			.handle('delete', () => Effect.void);
	})
);
```

### 3. Verify `App.ts` has no `DatabaseLive` on the Scalar layer

**File:** `backend-ts/apps/api/src/App.ts`

`HttpApiScalar.layer` only needs `HttpRouter` (per its signature at
`@effect-smol/packages/effect/src/unstable/httpapi/HttpApiScalar.ts:235-241`).
Providing `DatabaseLive` to it injects a `ConfigError` failure mode
into `AppLive.E`, which makes `Layer.launch` return
`Effect<never, ConfigError, never>` — also rejected by `runMain`.

The file should match this exactly. **Do not edit unless it doesn't.**

```ts
import { Api } from '@pawrrtal/api-core';
import { CoreModulesLive } from './Modules/Layers';
import { HttpApiBuilder, HttpApiScalar } from 'effect/unstable/httpapi';
import { Layer } from 'effect';

export const AppLive = Layer.mergeAll(
	HttpApiBuilder.layer(Api, { openapiPath: '/openapi.json' }).pipe(
		Layer.provide(CoreModulesLive)
	),
	HttpApiScalar.layer(Api, { path: '/docs' })
);
```

**Off by default:** no `.pipe(Layer.provide(DatabaseLive))` on the
Scalar line. When a future handler needs the DB, provide `DatabaseLive`
inside that handler's module — not on a route.

### 4. Verify `Main.ts` chain is correct

**File:** `backend-ts/apps/api/src/Main.ts`

The current shape is right. It should match this exactly. **Do not
edit unless it doesn't.**

```ts
import { NodeHttpServer, NodeRuntime } from '@effect/platform-node';
import { Layer } from 'effect';
import { createServer } from 'node:http';
import { HttpRouter } from 'effect/unstable/http';
import { AppLive } from './App';

const PORT = 8001;

const HttpServerLayer = HttpRouter.serve(AppLive).pipe(
	Layer.provide(NodeHttpServer.layer(createServer, { port: PORT })),
	Layer.orDie
);

Layer.launch(HttpServerLayer).pipe(NodeRuntime.runMain);
```

`Layer.orDie` collapses the `ServeError` from `NodeHttpServer.layer`
to `never` so the final Effect is `Effect<never, never, never>`. The
`HttpServer | Etag | FileSystem | HttpPlatform | Path` residuals from
`HttpApiBuilder.layer` are all covered by `NodeHttpServer.layer`'s
`HttpServer | NodeServices | HttpPlatform | Etag` outputs. `NodeServices`
includes `FileSystem` and `Path`
(`@effect-smol/packages/platform-node/src/NodeServices.ts:57`).

### 5. Verify `Modules/Layers.ts` is a plain `mergeAll`

**File:** `backend-ts/apps/api/src/Modules/Layers.ts`

With steps 1 + 2 applied, both inputs are `Layer<never, never, never>`,
so `CoreModulesLive` is `Layer<never, never, never>`. The file should
already be:

```ts
import { Layer } from 'effect';
import { HttpSystemLive } from './System/Http';
import { HttpProjectsLive } from './Projects/Http';

export const CoreModulesLive = Layer.mergeAll(HttpSystemLive, HttpProjectsLive);
```

**Do not edit unless it doesn't match.**

### 6. Run the typecheck

From the repo root:

```sh
just typecheck-backend-ts
```

Or directly:

```sh
cd backend-ts && bun install && bun run typecheck
```

**Pass criteria:** zero TypeScript errors. Hover `Layer.launch(HttpServerLayer)`
in your editor — it should resolve to `Effect<never, never, never>` and
the `.pipe(NodeRuntime.runMain)` call is accepted.

If a new error appears, read it carefully. Common follow-ups:

| Error shape | Cause | Fix |
|---|---|---|
| `ConfigError` in E channel | Someone re-added `.pipe(Layer.provide(DatabaseLive))` to a route that doesn't need it | Revert step 3 — drop the unnecessary provide |
| `Random` / `Clock` missing in R | A handler started using a service that wasn't there before (e.g. `Clock.currentTime` instead of `DateTime.nowUnsafe`) | Widen the `group` annotation in step 1 or 2 to `Layer.Layer<never, never, ServiceTag>` and provide the live service in `Layers.ts` |
| `Etag.Generator` / `HttpPlatform` missing | A platform was swapped out for one that doesn't bundle the same services | Add `Layer.provideMerge(PlatformLayer, NodeHttpServer.layer(...))` in step 4 |

### 7. Boot the API and smoke-test

```sh
just dev-backend-ts
```

In another terminal:

```sh
curl -i http://localhost:8001/api/v1/system/health
curl -i http://localhost:8001/openapi.json
curl -i http://localhost:8001/docs
```

**Pass criteria:**

| URL | Expected |
|---|---|
| `GET /api/v1/system/health` | `204 No Content` |
| `GET /openapi.json` | `200` with a JSON OpenAPI document |
| `GET /docs` | `200` with the Scalar HTML page |

## How it works (R-channel flow, before vs after steps 1+2)

| Step | R (before) | R (after) |
|---|---|---|
| `HttpApiBuilder.group(...)` (no services used) | `unknown` (from `as any`) | `never` (annotation) |
| `Layer.mergeAll(HttpSystemLive, HttpProjectsLive)` | `unknown` | `never` |
| `HttpApiBuilder.layer(Api, ...).pipe(Layer.provide(...))` | widens to `unknown` | `Etag \| FileSystem \| HttpPlatform \| Path` |
| `Layer.mergeAll(..., HttpApiScalar.layer(...))` | widens to `unknown` | `Etag \| FileSystem \| HttpPlatform \| Path` |
| `HttpRouter.serve(AppLive)` | widens to `unknown` | `HttpServer \| Etag \| FileSystem \| HttpPlatform \| Path` |
| `.pipe(Layer.provide(NodeHttpServer.layer(...)))` | widens to `unknown` | `never` (covered) |
| `.pipe(Layer.orDie)` | `unknown` | `never` |
| `Layer.launch(...)` | `Effect<never, never, unknown>` ❌ | `Effect<never, never, never>` ✓ |

## Rules

- **Off by default:** do not provide `DatabaseLive` on the Scalar
  route. Provide it inside the handler module that uses it.
- **Must not break:** the `as any` in `HttpApiBuilder.group` is a
  vendor cast
  (`@effect-smol/packages/effect/src/unstable/httpapi/HttpApiBuilder.ts:184`).
  We work around it with explicit annotations; do not patch
  `effect-smol`.
- **If you add a service-using handler:** widen the annotation to
  `Layer.Layer<never, never, ServiceTag>` and provide the live
  implementation in `Modules/Layers.ts`. Do not let R fall back to
  `unknown` again — re-run the R-flow table above mentally before
  merging.
- **Source of truth:** every API behaviour in this bean was verified
  against `backend/vendor/effect-smol` (the v4 vendor tree). Do not
  invent parallels; the canonical pattern in
  `ai-docs/src/51_http-server/10_basics.ts:50-57` is the contract.
