# Lesson 0003 — Prove the round trip, and parse at the trust boundary

Closes out Lesson 2. Two gates remain, and they're related: you never
proved `SessionStore.lookup` works against real Python, and the reason
you couldn't prove it cheaply is that you replaced *validation* with
*casts*. Fix the second and the first gets easier.

## Goal

1. `bun run scratchpad/session-lookup.ts` prints a real `User` fetched
   from the running Python API (`GET :8000/api/v1/users/me`) using a
   real `session_token` cookie.
2. The `lookup` path has **zero `as` casts**. The Python JSON is decoded
   through the `User` schema, so a bad/renamed/missing field surfaces as
   a `SessionStoreError` instead of silently sailing through.
3. `bun run typecheck` clean.

## Why this lesson exists

You shipped `decodeUser` (`SessionStore.ts:12-19`) as five `as` casts:

```ts
new User({ id: json.id as UserId, email: json.email as string, /* … */ })
```

The comment justifies it by saying `schemaBodyJson(User)` requires
`DecodingServices = unknown`. **That's a misdiagnosis** — and it's worth
understanding why, because it's the difference between a *trusted* and an
*untrusted* boundary.

- `Projects/Repo.ts:7-27` casts on purpose. Those rows come from **your
  own SQLite** — you wrote the `INSERT`, so the row already matches
  `Project`. The cast there dodges a real wrinkle: the **sync** decoder
  (`Schema.decodeUnknownSync`) surfaces a `DecodingServices` requirement
  it can't satisfy on a sync boundary. Direct construction is the
  honest call for trusted data on a sync path.
- `SessionStore.lookup` is the opposite case on both axes. The JSON comes
  from **Python** (a separate process you don't control — it can drift,
  redeploy, return `null`, rename `is_active`), and you're **already
  inside an Effect** (async), not on a sync boundary. So you get to use
  the async decoder, and the thing that bit Repo never applies.

`email` is the tell: your `User` validates email with a regex
(`Domain.ts:19`). Your cast means **that check never runs**. A garbage
email from Python becomes a "valid" `User`. That's the bug class this
lesson kills.

## The one concept: `schemaBodyJson` at the HTTP boundary

`HttpClientResponse.schemaBodyJson(schema)` reads the JSON body and
decodes it through `schema` in one step. Its signature
(`backend/vendor/effect-smol/packages/effect/src/unstable/http/HttpIncomingMessage.ts:80-86`):

```ts
schemaBodyJson<S extends Schema.Top>(schema):
  (self) => Effect.Effect<S["Type"], E | SchemaError, S["DecodingServices"]>
```

Read the `DecodingServices` slot. For a plain `Schema.Class` of
primitives + a branded `UserId` + a checked `Email`, **`DecodingServices`
is `never`** — no service to provide, no cast, no R-channel pain. That's
why the canonical reference calls it bare. If you ever *do* see `unknown`
there, the generic `S` failed to infer (usually you passed something
that isn't actually the class) — that's a signal to investigate, never to
cast past it.

## References (read these, in order — they ARE the answer)

| Source | What to extract |
|---|---|
| `backend/vendor/effect-smol/ai-docs/src/50_http-client/10_basics.ts:45-49` and `:58-66` | `schemaBodyJson(Schema.Class)` used twice, no cast, no service. `:47` shows wrapping the decode failure into a tagged error — exactly your `SessionStoreError` move. This is the shape you're copying. |
| `…/packages/effect/src/unstable/http/HttpIncomingMessage.ts:80-86` | The real signature. Confirm for yourself that the third type param is `S["DecodingServices"]`, and reason about why it's `never` for `User`. |
| `apps/api/src/Modules/Projects/Repo.ts:7-27` | The *contrast*: why casting trusted DB rows on a **sync** path is fine. Note what's different from your case (trusted vs external, sync vs async). |
| `apps/api/src/Modules/Auth/SessionStore.ts:12-19, 64-90` | What you're deleting (`decodeUser` + the `Effect.try`/`json` dance) and what you're replacing it with. |

## What to do (you write, I review)

1. **Curl Python first.** Get a real `session_token` (log in via the
   existing app, or curl the login route), then:
   `curl -i --cookie "session_token=<value>" http://localhost:8000/api/v1/users/me`.
   Confirm the field names and casing. (Good news: your `User` already
   uses snake_case — `is_active`, etc. — so it should line up. If decode
   later throws a `ParseError`, that's the schema catching a real
   mismatch, not noise.)
2. **Replace the decode in `lookup`.** Delete `decodeUser` and the
   `response.json` → `Effect.try` block. Use `schemaBodyJson(User)` on
   the response and keep your `Effect.mapError(... → SessionStoreError)`
   wrapper and `withSpan`. The reference at `10_basics.ts:45-49` is the
   template; you supply `User` and your error. Add the `HttpClientResponse`
   import.
3. **Confirm no casts remain** in `SessionStore.ts`. The `id: json.id as
   UserId` line and friends should be gone entirely.
4. **Write `apps/api/scratchpad/session-lookup.ts`.** It `yield*`s
   `SessionStore`, calls `lookup` with your real cookie value, and
   `Console.log`s the user. Provide `SessionStoreLive` (it bakes in the
   fetch client). Mirror the *structure* of `print-user.ts` — but the
   body, the cookie wiring, and the provide are yours to write.
5. **(Cleanup, while you're here)** `scratchpad/print-user.ts` is stale
   and would crash: it imports `…/Modules/Authentication/Domain` (now
   `…/Auth/Domain`) and prints `user.name` (the field is gone — `User`
   has `email` now). Fix the import and the field, or delete it.

## What I won't do

- Write the `schemaBodyJson(User)` call.
- Write the scratchpad body or the cookie plumbing.
- Hand you the import line.

Stuck after reading `10_basics.ts`? Bring your partial `lookup` and ask a
specific question.

## Verify (what "done" looks like)

```sh
# 1. Python is up and the cookie is valid
curl -i --cookie "session_token=<value>" http://localhost:8000/api/v1/users/me

cd backend-ts/apps/api
bun run scratchpad/session-lookup.ts   # prints a real User from Python
bun run typecheck                       # clean, and grep shows no `as` in SessionStore.ts
```

Round trip printing a real user is gate 1. Typecheck-with-no-casts is
gate 2.

## Things that might trip you up (hints, not solutions)

| Symptom | What it means |
|---|---|
| `schemaBodyJson(User)` shows `DecodingServices = unknown` in R | `User` isn't inferring as the class. Check you imported the `User` class (not a type), and that you passed the class itself. Don't cast past it. |
| `SchemaError` / `ParseError` at runtime | The schema is doing its job — Python returned a field that doesn't match `User`. Re-curl, compare field names/types. This is the bug the casts were hiding. |
| `fetch failed` | Python isn't on `:8000`. Start it. |
| `401` | Stale/wrong `session_token`. Re-auth. |
| `Service not found: SessionStore` | Scratchpad didn't `Effect.provide(SessionStoreLive)`. |

## What Lesson 4 will add (don't write yet)

The `Authentication` middleware (`HttpApiMiddleware`,
`packages/api-core/src/Modules/Auth/Api.ts` — currently a stub). It reads
the cookie off the request, calls `SessionStore.lookup`, and **provides**
`CurrentUser` to every handler in the group. That's where
`CurrentUser.Live` is born and where `SessionStore` finally gets a
consumer. The typed `AuthenticationError` (401) lands there too.

## Followups

- "Why is Repo allowed to cast but I'm not?" → trusted DB vs untrusted
  HTTP, and sync decoder vs async. Re-read `Repo.ts:7-27` against
  `HttpIncomingMessage.ts:80-86`.
- "When would `DecodingServices` actually be non-`never`?" → when a
  schema field needs a service to decode (e.g. a transform that does
  I/O). `User` has none, so it's `never`.

## Status

**Not started.** Next: Lesson 4 — the `Authentication` middleware.
