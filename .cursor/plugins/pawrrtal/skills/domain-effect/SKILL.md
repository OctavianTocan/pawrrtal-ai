---
name: domain-effect
description: "Use when writing or reviewing Pawrrtal Effect TypeScript code in backend-ts: API contracts, HttpApi handlers, services, repos, layers, tagged errors, Effect tests, streams, SQL, auth middleware, or vendor-source API checks."
paths:
  - "backend-ts/**/*.ts"
  - "backend/vendor/effect-smol/**"
---

# Effect TS in Pawrrtal

Pawrrtal's Effect workspace is `backend-ts/`:

- `backend-ts/packages/api-core` (`@pawrrtal/api-core`) owns shared contracts:
  domain schemas, tagged errors, HttpApi groups, and root `Api`.
- `backend-ts/apps/api` (`@pawrrtal/api`) owns runtime wiring: HTTP handlers,
  services, repos, policies, infrastructure layers, auth, and `Main.ts`.
- `backend/vendor/effect-smol` is the Effect v4 beta source of truth. Do not
  infer APIs from Effect v3 docs or `backend/vendor/effect`.

Current package pins: `effect@4.0.0-beta.74` and matching `@effect/*` platform
packages. Do not `file:` link `effect-smol`; it contains internal workspace
references.

## Before Writing Code

1. Read the local module you are changing plus its caller and tests.
2. Check `backend/vendor/effect-smol/ai-docs/` or source for any API you are
   about to use.
3. Keep Python on `:8000` canonical until route parity; Effect TS runs on
   `:8001` for the strangler slice.
4. Run the scoped gate for your change: usually `cd backend-ts && bun run typecheck`
   plus `cd backend-ts && bun run test` when behavior changed.

## Rules

- Contracts live in `@pawrrtal/api-core`; runtime behavior lives in
  `@pawrrtal/api`.
- Http handlers unpack input, call services, apply auth/policy, and translate
  boundary errors. They do not own mutable state.
- Services own business rules and dependency composition.
- Repos own SQL/storage details and return raw persistence shapes; decode into
  domain types at service boundaries.
- Tagged errors are data. Use `Schema.TaggedError` for expected failures and
  keep error channels explicit.
- Prefer `Effect.Service` for application services. Use `Context.Tag` for
  injected resources, config bags, and test seams.
- Do not preserve compatibility with in-progress branch shapes. Update
  consumers directly.

## References

- [Module Structure](references/module-structure.md)
- [Services And Layers](references/services-layers.md)
- [HTTP API](references/http-api.md)
- [Testing](references/testing.md)
