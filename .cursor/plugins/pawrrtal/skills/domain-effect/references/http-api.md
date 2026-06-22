# HTTP API

Pawrrtal uses Effect v4 beta `HttpApi` patterns from `backend/vendor/effect-smol`.
Check `backend/vendor/effect-smol/ai-docs/51_http-server/10_basics.ts` before
changing API syntax.

## Contract Layer

Put endpoint declarations in `backend-ts/packages/api-core/src/Modules/<Name>/Api.ts`.
Contracts should contain schemas and endpoint definitions only. They must not
construct services, read env vars, allocate refs, or own mutable state.

## Runtime Layer

Put handlers in `backend-ts/apps/api/src/Modules/<Name>/Http.ts`.

Handlers should:

- Unpack route params, query, headers, and payload.
- Pull the authenticated user from the provided auth middleware when protected.
- Call `Service.ts`.
- Map expected service errors to public tagged API errors.
- Return domain response values.

Handlers should not:

- Query SQL directly.
- Store mutable state in module scope.
- Decide provider/channel behavior.
- Start servers in tests.

## Auth

Auth runtime lives in `backend-ts/apps/api/src/Modules/Authentication/`.
Protected groups should provide `HttpAuthLive` on the group layer that needs it,
not only at the root module layer.

When mapping session store failures, convert `SessionStoreError` to
`AuthenticationError` at `sessionStore.lookup()`, not on `provideService`.

## Health

The system health endpoint is top-level `GET /api/v1/health` (`SystemApi`), not
`/api/v1/system/health`.
