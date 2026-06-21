# Lesson 0002 — `SessionStore` with real cookie → Python

## Attempt 1 review — 2026-06-18

**Where you are:** `SessionStore.ts` is written; `scratchpad/session-lookup.ts`
is *not*. Typecheck passes — but only because of `as` casts (see below), so the
round trip is still unproven.

**Landed — keep these:**

- The `Layer.effect` + `yield* HttpClient` + `return { lookup } as const` +
  `Layer.provide(…)` shape. It matches `Projects/Service.ts:117-178`. This was
  the whole point of the lesson.
- Identifier `'@apps/api/Auth/SessionStore'` — right convention.
- You reached past what I prescribed: `HttpClientResponse.filterStatusOk` +
  `schemaBodyJson(User)` instead of manual `.json` → `decodeUnknown`. That's the
  more idiomatic v4 path. Keep it.

**Fix before this is done:**

1. **Kill the `as` casts** (`SessionStore.ts:41-43` and `:54-57`). A cast forces
   `tsc` green by lying to it — and inference is supposed to *prove* your wiring
   is correct. Delete both, re-run typecheck, and read the real error. The
   canonical `50_http-client/10_basics.ts` never casts: it reconciles the error
   channel with `Effect.mapError` and provides the client with
   `.pipe(Layer.provide(FetchHttpClient.layer))` (one layer, not an array).
   Compare yours against it and make the declared `lookup` type match what's
   actually inferred. (My earlier guess that it was a missing `Scope` was wrong —
   that example proves `get` → `schemaBodyJson` leaks no `Scope`; it's an
   error-channel mismatch.)
2. **Write `scratchpad/session-lookup.ts`.** It printing a real User is gate 1.
   Typecheck is only gate 2.
3. **Curl Python first (step 1 — you skipped it).** When you decode, watch field
   casing: `User` is camelCase (`isActive`…); FastAPI usually returns snake_case
   (`is_active`…). That mismatch is the ParseError trap below.

**Deviation (fine):** you surfaced `HttpClientError | SchemaError` instead of the
`Effect<User, never>` (orDie) I scoped for Lesson 2. Defensible — just know
Lesson 3 rewires the error channel.

## Goal

By the end you have a `SessionStore` service that, given a session
cookie value, makes a real HTTP call to
`http://localhost:8000/api/v1/users/me` and returns a typed `User`.
You have a scratchpad that proves the round trip.

## Why this lesson exists

Every real service in this codebase is a `Layer.effect` — a body that
`yield*`s dependencies and builds the value. You've seen the shape
once in `Projects/Service.ts:117-178`. This lesson is you writing
that shape from scratch for the first time, with `HttpClient` as the
dependency.

## Concepts (2 — read the references, don't expect me to re-explain them)

1. **`Layer.effect(Class, Effect.gen(function*() { … }))`** — the
   shape you'll write.
2. **`HttpClient.HttpClient`** — Effect's I/O seam. `yield*` it, call
   `.get(url, { headers })`, decode the response.

That's it. The rest is reading.

## Where the shape lives (read these yourself, in order)

| Source | What to extract |
|---|---|
| `backend-ts/apps/api/src/Modules/Projects/Service.ts:117-178` | The exact `Layer.effect` + `yield* ProjectsRepo` + `Layer.provide(...)` shape you're copying. Read this twice. |
| `backend/vendor/effect-smol/ai-docs/src/01_effect/02_services/01_service.ts:22-37` | The class + static `Layer.effect` + `Class.of(...)` pattern |
| `backend/vendor/effect-smol/ai-docs/src/01_effect/02_services/20_layer-composition.ts:24-49` | `Layer.effect` with a dependency — same shape, `SqlClient` instead of `HttpClient` |
| `backend/vendor/effect-smol/ai-docs/src/50_http-client/10_basics.ts` | v4 `HttpClient` service and `FetchHttpClient.layer`. Read the whole file — it's the closest match to what you're building, and it never needs an `as` cast. |
| `backend/vendor/comcom/apps/api/src/Modules/Authentication/Services/Auth.ts:181-232` | The v3 ancestor: `authenticateSession(token)` calls `betterAuth.api.getSession(...)` — your `lookup(cookie)` is the same idea over HTTP |

## What to build (your typing, your time)

1. **Curl the Python endpoint.** Find the cookie name and the
   response shape. You need both before you can write the `lookup`
   body.
2. **Read `Projects/Service.ts:117-178`.** Notice: the `Layer.effect`
   body has a `yield*` for the dependency and a `return` for the
   service instance. That's the shape.

### The `lookup` algorithm (5 steps in plain English)

You'll get stuck on "what do I type inside the function." The
answer is to think of it as 5 simple steps; you translate each
into the right Effect call:

1. URL = `http://localhost:8000/api/v1/users/me` (hardcode it).
2. Call the HttpClient's `get` method with that URL and a
   `headers` option. The header you need is
   `Cookie: session_token=<the cookie value>`.
3. The response has a `.json` method. Call it. You get an
   `unknown`.
4. Pass that `unknown` through `Schema.decodeUnknown(User)(...)`
   to get a `User`. For now, `Effect.orDie` on the result — Lesson
   3 swaps in a typed error.
5. Return the User.

The function body is `Effect.gen(function*() { yield*; yield*;
yield*; return ...; })`. Three yields, one return.

For the **exact syntax** of steps 2 and 3, smol's `HttpClient`
ai-docs at `50_http-client/10_basics.ts` has working code. For
step 4, the same `Schema.decodeUnknown` shape you used in Lesson
1.

3. **Write `backend-ts/apps/api/src/Modules/Auth/SessionStore.ts`.**
   You decide: file structure, identifier string, method name, what
   `lookup` does when the cookie is bad (for now, just let it fail —
   Lesson 3 introduces the typed error).
4. **Provide `HttpClient` somewhere up the chain.** The `Live` layer
   needs a real `HttpClient.HttpClient` implementation. The v4 smol
   convention is `FetchHttpClient.layer` — read smol's ai-docs to
   find the import.
5. **Write `backend-ts/apps/api/scratchpad/session-lookup.ts`.**
   Calls `lookup` with a real cookie, prints the result.
6. **Verify.**

## What I won't do

- Hand you the `Layer.effect` body.
- Hand you the `client.get(...)` call.
- Hand you the `Schema.decodeUnknown` step.
- Hand you the scratchpad code.

If you get stuck, the references above have the answers. Read them.
If you're still stuck after reading, ask me a *specific* question —
but bring your partial code.

## Things that might trip you up (hints, not solutions)

| Symptom | What to read |
|---|---|
| `Service not found: HttpClient` | You need a `Layer.provide(FetchHttpClient.layer)` somewhere in the runtime chain. Find the smol reference for the import. |
| `Schema.decodeUnknown(User)(json)` returns a `ParseError` | Your `User` shape doesn't match what Python returns. Re-curl; align the schema. |
| `fetch failed` | Python isn't running on `:8000`. Start it. |
| `401 Unauthorized` | Stale cookie or wrong cookie name. Re-curl. |
| Typecheck only passes with an `as` cast | You're hiding a type mismatch (usually the error channel, not `Scope`). `50_http-client/10_basics.ts` never casts — reconcile your declared `lookup` type with what's inferred. |

## Verify (what "done" looks like)

```sh
cd backend-ts/apps/api
bun run typecheck                                 # clean — with NO `as` casts
bun run scratchpad/session-lookup.ts              # prints a real User from Python
```

The moment `bun run scratchpad/session-lookup.ts` prints a real user
(not an error), Lesson 2 is done. Typecheck is the second gate.

## What Lesson 3 will add

`HttpApiMiddleware.Service<Authentication>()('Authentication', { provides, security, error })`. The middleware body becomes
`Effect.provideService(httpEffect, CurrentUser, user)`. Lesson 3
introduces a typed `AuthenticationError` (status 401) and rewires
`lookup` to surface it. Don't try to write that today.

## Cross-references

- v4 `Layer.effect`: `backend/vendor/effect-smol/ai-docs/src/01_effect/02_services/01_service.ts:22-37`
- v4 `Layer.effect` with deps: `backend/vendor/effect-smol/ai-docs/src/01_effect/02_services/20_layer-composition.ts:24-49`
- v4 `HttpClient` + `FetchHttpClient.layer`: `backend/vendor/effect-smol/ai-docs/src/50_http-client/10_basics.ts`
- v3 ancestor (comcom): `backend/vendor/comcom/apps/api/src/Modules/Authentication/Services/Auth.ts:181-232`
- Pawrrtal live Python seam: `GET http://localhost:8000/api/v1/users/me` with `Cookie: <value>` (you curl this in step 1)

## Followups

Ask if you're stuck. Specifically:

- "I can't tell where `HttpClient` is supposed to come from." → read
  the smol `Layer.effect` example that uses a dependency.
- "My `lookup` body is too long / branching out of control." → it
  should be 3-5 lines; if it's longer, you're doing something the
  middleware should be doing.
