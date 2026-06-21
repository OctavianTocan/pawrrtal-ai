# Next-lesson arc decided + parse-at-trust-boundary

After auditing the live codebase against the lessons, the remaining arc
is locked to three lessons mapped onto the mission's open goals:

- **Lesson 3 (`0003`, written):** close out `SessionStore` — prove the
  real round trip (`scratchpad/session-lookup.ts`) and replace the
  field-level `as` casts in `decodeUser` with `schemaBodyJson(User)`.
- **Lesson 4:** the `Authentication` `HttpApiMiddleware` — fill in the
  `Api.ts` stub (`provides: CurrentUser`, cookie `security`, `failure`),
  add `AuthenticationError` (401) in `Auth/Errors.ts`, write
  `apps/api/.../Auth/Http.ts`. First real consumer of `SessionStore`;
  birth of `CurrentUser.Live`. (Mission goal: `yield* CurrentUser` in
  handlers.)
- **Lesson 5:** kill `STUB_USER_ID` in `Projects/Http.ts` + teach
  `Layer.provide` vs `Layer.provideMerge` while wiring the middleware's
  deps. (Mission goals: new endpoint w/o copying handlers, provide vs
  provideMerge, STUB gone.)

## Decision: parse at the trust boundary

User chose to make this a teaching point, not just a cleanup. Rule going
forward: **Schema-decode external/untrusted JSON (HTTP from Python);
direct-construct + cast only trusted data on a sync boundary (own DB
rows, as `Projects/Repo.ts:7-27` does).** The `SessionStore.ts` comment
claiming `schemaBodyJson(User)` needs `DecodingServices = unknown` is a
misdiagnosis: for a plain `Schema.Class`, `DecodingServices` is `never`
(proven by `10_basics.ts:45-66` and the signature at
`HttpIncomingMessage.ts:80-86`). The Repo friction is specific to the
*sync* decoder, which doesn't apply inside `lookup` (already async).

## Drift found during the audit (not yet fixed)

1. `apps/api/scratchpad/print-user.ts` is stale and would crash —
   imports `…/Modules/Authentication/Domain` (renamed to `…/Auth/Domain`)
   and prints `user.name` (no longer a field; `User` now has `email`,
   `is_active`, `is_superuser`, `is_verified`). Folded into Lesson 3 as a
   cleanup step.
2. `apps/api/test/` has empty duplicate dirs `fixtures 2/`, `Modules 2/`,
   `unit 2/` — macOS copy/sync artifacts. Safe to delete; not
   teaching-relevant.
3. `User` grew past what Lesson 1 documents (now 5 fields mirroring
   Python's `/users/me`). Lesson 1's inline snippet is illustrative, not
   current — fine, but note it if revisited.
