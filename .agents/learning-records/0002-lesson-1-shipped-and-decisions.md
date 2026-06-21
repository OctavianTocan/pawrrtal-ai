# Lesson 0001 shipped

User shipped `Domain.ts` with `User` (id + name + validated email),
`CurrentUser` (class form, identifier `'@apps/api/Auth/CurrentUser'`),
and a working scratchpad. `bun run scratchpad/print-user.ts` prints
`User: John Doe (john@doe.com)`. Typecheck clean.

## Decisions locked

- **Identifier format:** `'@apps/api/<Name>'` (comcom convention). User
  chose this over the npm-scope form. **Applies to api-core services too
  — they get `'@apps/api-core/<Name>'`.** This affects every service
  identifier in Lessons 2-4.
- **Static layer naming:** `Test` for hard-coded, `Live` for the runtime
  impl (Pawrrtal-Http.ts precedent). `Default` (comcom) and `layer`
  (smol) rejected for Pawrrtal.

## Implication for next session

Lesson 2 builds `static readonly Live = Layer.effect(...)` on
`CurrentUser`, with a `SessionStore` dependency that the middleware
(Lesson 3) will plug a real cookie into. Skip directly to Lesson 3 if
the user wants cookie-reading before service composition — but the
`Layer.effect` shape needs to land somewhere first, and `CurrentUser.Live`
is the natural home.

## Rebase findings (2026-06-14)

After rebase onto latest main, three drift items discovered and fixed:

1. **Identifier inconsistency.** `Projects/Service.ts:90` and
   `Projects/Repo.ts:45` were using the npm-scope form
   (`'@pawrrtal/api/...'`). User chose comcom form everywhere; both
   renamed to `'@apps/api/Projects/Service'` and `'@apps/api/Projects/Repo'`.
2. **Stale test fixture deleted.** A pre-existing
   `test/fixtures/current-user-test.ts` defined a *parallel* `CurrentUser`
   service with a slimmer shape (`{ userId: UserId }`) and an npm-scope
   identifier. It pre-dated the api-core `CurrentUser` design and
   nothing imported it. Deleted; the api-core `CurrentUser.Test` is
   the replacement for any future test fixture needs.
3. **Lessons updated.** `Lesson 1` adds a 2-line "What is the `Test`
   layer for?" note to clear the lingering `// Not entirely sure`
   comment in `Domain.ts:20-21`. `Lesson 2` now points at
   `Projects/Service.ts:117-178` as the **primary Pawrrtal reference**
   for `Layer.effect` (was: smol + comcom only).
