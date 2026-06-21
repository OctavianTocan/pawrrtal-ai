# Retro after Lesson 1

## What changed in the plan

- **Lesson 2 scope:** User picked option B (real cookie → Python) over the
  stub I recommended. Lesson 2 now teaches `Layer.effect` + `HttpClient` +
  Python call instead of just the `Layer.effect` shape with a hardcoded map.
- **Error class scope:** User chose "Lesson 3 with middleware." Lesson 2's
  `SessionStore.lookup` returns `Effect<User, never>` — untyped failure. The
  `Schema.TaggedErrorClass` + `{ httpApiStatus: 401 }` shape lands in
  Lesson 3 alongside the middleware that catches it.
- **Pace:** "Faster — you write, I review" (same as Lesson 1). Don't
  pre-scaffold code unless asked.

## Blockers observed in Lesson 1

1. `Effect.succeed` used where `Layer.succeed` was needed (different
   module, different return type). Caught by typecheck. Reinforce the
   module boundary in Lesson 2.
2. `UserId.make(1)` on a non-branded schema. `.make()` only exists on
   `Schema.brand(...)` outputs. Caught by typecheck. Don't re-introduce
   in Lesson 2; pass a real value.

## Reusable pattern

The two bugs above both surfaced because the user trusted that an API
existed that didn't, on a different module. Generalised rule for future
lessons: when introducing a new combinator (Layer.effect, HttpClient, etc.),
**call out the module it lives in and what it returns**. Save the
typecheck for catching mismatches, not for teaching the API surface.

## Next milestone

Lesson 2 done when
`backend-ts/apps/api/scratchpad/session-lookup.ts` prints a real User
from `GET http://localhost:8000/api/v1/users/me` and
`bun run --filter '@pawrrtal/api-core' typecheck` stays clean.
