# Lesson 0001 — `CurrentUser` as a `Context.Service` you can `yield*`

## Goal

By the end you can read this and not flinch:

```ts
export class User extends Schema.Class<User>("User")({
  id: UserId,
  name: Schema.String,
}) {}

export class CurrentUser extends Context.Service<CurrentUser, User>()(
  "@apps/api/Auth/CurrentUser"
) {
  static readonly Test = Layer.succeed(
    CurrentUser,
    new User({ id: "00000000-0000-0000-0000-000000000001", name: "Ada" })
  )
}
```

…and you can `yield* CurrentUser` from any Effect program and get a
typed `User` back.

## Why this lesson exists

Auth in our strangler is *just* a `Context.Service` that the HTTP layer
populates from a cookie. Everything else in Lessons 2-4 is decoration on
this pattern. The comcom reference implements the same idea with
`AuthContext`
(`backend/vendor/comcom/packages/comcom/api-core/src/Modules/Authentication/Domain.ts:116-119`)
— they call it `AuthContext` and put a richer object inside, but the
shape is identical. v4's `Context.Service` is the v3 `Context.Tag`
rewritten as a class with a static `layer` shortcut.

## Concepts (3 — nothing more)

1. **`Context.Service<Identity, Interface>()('id')`** — defines a typed
   service bag. v4 idiom is the **class** form, not the bare `Tag` form
   (smol: `.patterns/effect.md:92-102` mandates this; v3 comcom used the
   bare `Context.Tag` form — see
   `AuthContext extends Context.Tag('...')<AuthContext, Auth>() {}`).
2. **`yield* ServiceName`** — consumes a service from the Effect
   environment. This is the only verb for "give me what's been provided."
3. **`Layer.succeed(Class, value)`** — the simplest "this value IS the
   service" layer. v4 short-form. We'll swap it for `Layer.effect` in
   Lesson 2 (smol:
   `ai-docs/src/01_effect/02_services/01_service.ts:22-37` shows
   `Layer.effect`; `Layer.succeed` is the constant-value twin).

### On the `Test` static layer

The `static readonly Test = Layer.succeed(CurrentUser, new User({...}))`
line is a **test fixture** — a hard-coded service value used by scratchpad
programs, unit tests, and dev tooling. It's the same `Context.Service`
shape as the runtime one, but its body is a constant instead of a
`Layer.effect` that `yield*`s real I/O. You'll see this pattern on
every service in the codebase: `Test` for hard-coded, `Live` (Lesson 2)
for the runtime implementation. **You can delete the
`// Not entirely sure what this is for` comment in `Domain.ts:20-21` now.**

## Where the v4 shape comes from (read these in order)

| Source | What it shows |
|---|---|
| **Pawrrtal** `backend-ts/apps/api/src/Modules/Projects/Service.ts:65-90, 117-178` | The class form + static `Live` (`Layer.effect`) + `Live` (`Layer.provide`) — read this first, it's the closest reference |
| `backend/vendor/effect-smol/.patterns/effect.md:92-102` | Why class syntax; no `Service` suffix in identifier |
| `backend/vendor/effect-smol/ai-docs/src/01_effect/02_services/01_service.ts:13-37` | The exact class + static-layer pattern (smol's `Database` example) |
| `backend/vendor/effect-smol/ai-docs/src/51_http-server/fixtures/api/Authorization.ts:5` | `CurrentUser` as a `Context.Service` (the v4 canonical) |
| `backend/vendor/effect-smol/ai-docs/src/51_http-server/fixtures/server/Authorization.ts:7-35` | The middleware that *consumes* the cookie and **provides** `CurrentUser` (Lesson 3 will copy this) |
| `backend/vendor/comcom/packages/comcom/api-core/src/Modules/Authentication/Domain.ts:58-119` | The v3 ancestor — `Auth`, `AuthContext`, `Context.Tag` form (read for context, write v4) |
| Pawrrtal `Projects/Domain.ts:24-43` | The `Schema.Class` template to mirror for `User` |

## State on disk (read this first)

The `Domain.ts` file is **already stubbed** with a `CurrentUser` class
that has two mistakes. You replace the file, you don't add to it.

Current stub:

```ts
export class CurrentUser extends Context.Service<CurrentUser, { User: Schema.Class<User> }>()(
  "@pawrrtal/api/Authentication/CurrentUser"
)
```

Mistakes in the stub:

- **Identifier format.** Stub uses `'@pawrrtal/api/Authentication/CurrentUser'`.
  Pawrrtal follows comcom's `'@apps/api/<Name>'` rule. Use
  `'@apps/api/Auth/CurrentUser'`.
- **Interface is wrapped in an object literal.** `{ User: Schema.Class<User> }`
  makes the interface a one-key object whose key is `User`. Drop the wrapper —
  the second type param wants the type *itself*, so just `User`.

## What to do (you write, I review)

1. **Replace** `backend-ts/packages/api-core/src/Modules/Authentication/Domain.ts`.
   Keep it as the contract file — no `Layer.effect` bodies, no DB, no HTTP.
2. **Define `User` as a `Schema.Class<User>('User')`**, mirroring
   `Project` in `Projects/Domain.ts:24-43`. Use the existing `UserId`
   schema from `Lib/TypeIds.ts:19` for the `id` field. (Don't redefine
   `UserId` — `Project.user_id` already uses it.)
3. **Define `CurrentUser` as `Context.Service<CurrentUser, User>()('…')`**
   with the corrected identifier.
4. **Add the test layer**:
   `static readonly Test = Layer.succeed(CurrentUser, new User({ id: "00000000-0000-0000-0000-000000000001", name: "Ada" }))`.
   Note `new User(...)`, not `User.of({...})` — `Schema.Class` instances
   are constructed with `new`.
5. **Create** `backend-ts/apps/api/scratchpad/print-user.ts`:

   ```ts
   import { Console, Effect } from "effect"
   import { CurrentUser } from "@pawrrtal/api-core/Modules/Authentication/Domain"

   const program = Effect.gen(function* () {
     const user = yield* CurrentUser
     yield* Console.log(`hello, ${user.name}`)
   }).pipe(Effect.provide(CurrentUser.Test))

   Effect.runPromise(program)
   ```

6. **Run:** `cd backend-ts/apps/api && bun run scratchpad/print-user.ts`.
7. **Expected:** `hello, Ada`.

## Sanity checks (don't skip)

- [ ] The class extends `Context.Service<…>` (the class form), not
      `Context.Tag<…>` (the v3 form).
- [ ] The identifier string is `'@apps/api/Auth/CurrentUser'` — matches
      comcom's `'<scope>/<pkg>/<Module>'` rule (comcom:
      `Sessions/Service.ts:51`).
- [ ] The Interface param is the bare `User` class — not `{ User: ... }`.
- [ ] `User` is constructed with `new User({...})`, not `User.of({...})`.
- [ ] `UserId` is imported from `Lib/TypeIds` (or re-exported from
      `Modules/Authentication/Domain`), not redefined.
- [ ] `Layer.succeed` takes the **class as Tag** + the **value as the
      service interface** — not a primitive.
- [ ] No `try`/`catch` inside `Effect.gen` (smol:
      `.patterns/effect.md:3-29` forbids it).

## Common errors and what they mean

| Error | Cause |
|---|---|
| `Property 'name' does not exist on type 'Effect<...>'` | The Interface param is wrong. Re-check `Context.Service<CurrentUser, User>()`. |
| `Service not found` at runtime | `Effect.provide(CurrentUser.Test)` is missing or imported from the wrong file. |
| `Expected 1 argument, but got 0` on `new User(...)` | You defined `User` as a `Schema.Struct` (plain object), not a `Schema.Class`. Use the class form. |
| `Cannot find name 'Context'` | Import missing: `import { Context, Effect, Layer, Schema } from "effect"`. |
| `Type 'User' is missing the following properties from type 'User'` | You probably have two `User`s in scope (one from your file, one from an auto-import). Re-check your imports. |

## What Lesson 2 will add

`Layer.succeed` is a constant. `Layer.effect` is a builder — its body is
an `Effect.gen` that can `yield*` *other* services. The seam is:

```ts
// Lesson 1 (this lesson)
static readonly Test = Layer.succeed(CurrentUser, new User({...}))

// Lesson 2 (preview — don't write yet)
static readonly Live = Layer.effect(
  CurrentUser,
  Effect.gen(function* () {
    const sessionStore = yield* SessionStore  // <-- this is where the cookie goes
    return new User({ id: "00000000-0000-0000-0000-000000000001", name: "Ada" })
  })
)
```

That `yield* SessionStore` is where Pawrrtal's "look up user from cookie"
plugs in. The comcom equivalent is `AuthService.authenticateSession(token)`
that calls `betterAuth.api.getSession(...)` (comcom:
`apps/api/src/Modules/Authentication/Services/Auth.ts:181-232`).

## Cross-references

- **v4 pattern doc**: `backend/vendor/effect-smol/LLMS.md:97-147` (services section)
- **v4 HttpApi shape that will consume this**: `backend/vendor/effect-smol/ai-docs/src/51_http-server/fixtures/server/Users/http.ts:63-66`
- **Pawrrtal live seam you'll close**: `backend-ts/apps/api/src/Modules/Projects/Http.ts:12, 24-35` (the `STUB_USER_ID`)
- **Pawrrtal `Schema.Class` template to mirror**: `backend-ts/packages/api-core/src/Modules/Projects/Domain.ts:24-43`
- **Existing `UserId` schema to reuse**: `backend-ts/packages/api-core/src/Lib/TypeIds.ts:19`
- **Comcom v3 ancestor (read for shape, do not copy)**: `backend/vendor/comcom/packages/comcom/api-core/src/Modules/Authentication/Domain.ts:116-119`

## Followups

Ask me anything. Specifically:

- Why is the class form mandatory in v4?
  (`.patterns/effect.md:92-102` — answer: discoverability of the static `layer`.)
- When do I reach for `Context.Reference` instead?
  (smol: `ai-docs/src/01_effect/02_services/10_reference.ts` — for config values, not services.)
- Why does the v4 identifier not have `Service` in it?
  (`.patterns/effect.md` — the class name already carries that info;
  duplication is noise.)

## Status

**Completed 2026-06-14.** See
`learning-records/0002-lesson-1-shipped-and-decisions.md` for what
shipped and the decisions locked. Next: Lesson 2 — `Layer.effect`
for `CurrentUser.Live`.
