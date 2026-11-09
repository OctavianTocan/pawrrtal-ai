---
name: domain-effect
description: "Use when writing or reviewing Pawrrtal Effect TypeScript code in backend-ts: API contracts, HttpApi handlers, services, repos, layers, tagged errors, Effect tests, streams, SQL, auth middleware, or vendor-source API checks."
paths:
  - "backend-ts/**/*.ts"
  - "backend/vendor/effect-smol/**"
---

# Effect TS in Pawrrtal

Pawrrtal's Effect workspace is `backend-ts/`:

- `backend-ts/packages/domain-core` (`@pawrrtal/domain-core`) owns shared
  transport-neutral contracts: domain schemas, ids, branded values, and public
  tagged errors used by HTTP, RPC, harness, services, and tests.
- `backend-ts/packages/api-core` (`@pawrrtal/api-core`) owns HTTP/OpenAPI
  contracts only: `HttpApi` groups, endpoint declarations, OpenAPI
  annotations, and root `Api`.
- `backend-ts/packages/rpc-core` (`@pawrrtal/rpc-core`) owns Effect RPC
  protocol contracts only. It imports shared schemas/errors from
  `domain-core`; it must not import from `api-core`.
- `backend-ts/packages/harness` (`@pawrrtal/harness`) owns provider lifecycle,
  adapters, normalized streams, cancellation, continuation, and conformance. It
  may import `domain-core`, but not HTTP/RPC app handlers.
- `backend-ts/apps/api` (`@pawrrtal/api`) owns HTTP runtime wiring: handlers,
  services, repos, policies, infrastructure layers, auth, and `Main.ts`.
- `backend-ts/apps/rpc` owns RPC runtime wiring: protocol handlers, streaming
  transport, auth/profile boundary, and app composition.
- `backend/vendor/effect-smol` is the Effect v4 beta source of truth. Do not
  infer APIs from Effect v3 docs or `backend/vendor/effect`.

Current package pins: `effect@4.0.0-beta.93` and matching `@effect/*` platform
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

- For new 006+ Effect TS work, shared schemas/errors live in
  `@pawrrtal/domain-core`; HTTP contracts live in `@pawrrtal/api-core`; RPC
  contracts live in `@pawrrtal/rpc-core`; runtime behavior lives in app
  packages.
- Existing modules may still keep schemas/errors in `api-core`; when touching
  those boundaries for new work, move toward the split instead of deepening the
  old coupling.
- Do not put `RpcProtocol.ts` in `api-core`. Put RPC protocol declarations in
  `rpc-core`, RPC handlers in `apps/rpc`, and HTTP handlers in `apps/api`.
- `rpc-core` must not import `api-core`, and `api-core` must not import
  `rpc-core`; both should depend on `domain-core` when they share shapes.
- The provider harness is a reusable library boundary, not an API transport. It
  should not define HTTP routes or RPC handlers.
- For the 006 session engine, use `Sessions` as the canonical domain module and
  remove/replace the old backend-ts `Conversations` practice module. Do not add
  new provider execution behavior under `Conversations`.
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
- [RPC And Shared Contracts](references/rpc-and-contracts.md)
- [Testing](references/testing.md)
