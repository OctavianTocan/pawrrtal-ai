/**
 * `Authentication` — HttpApi middleware contract (api-core side).
 *
 * Mirrors comcom's `HttpApiMiddleware.Tag<Authentication>()('Authentication', { provides, security, failure })`
 * in v4 form (`HttpApiMiddleware.Service`). The `provides: CurrentUser`
 * declaration is what makes `yield* CurrentUser` work inside every
 * handler attached to a group that uses `.middleware(Authentication)`.
 *
 * **Status: stub.** Lesson 3 fills in `provides`, `error`, and
 * `security`; the implementation lands in `apps/api/.../Auth/Http.ts`
 * (also Lesson 3).
 *
 * v4 reference: `backend/vendor/effect-smol/ai-docs/src/51_http-server/
 * fixtures/api/Authorization.ts:16-36`.
 */

import { HttpApiMiddleware } from 'effect/unstable/httpapi';

/**
 * Auth middleware contract. The `provides: CurrentUser` declaration
 * (filled in during Lesson 3) is what makes `yield* CurrentUser` work
 * inside every handler attached to a group via `.middleware(Authentication)`.
 */
export class Authentication extends HttpApiMiddleware.Service<Authentication>()('Authentication', {
	// provides: CurrentUser,
	// failure: Schema.Union(AuthenticationError, InternalError),
	// security: {
	// 	cookie: HttpApiSecurity.apiKey({ in: 'cookie', key: SESSION_COOKIE }),
	// 	bearer: HttpApiSecurity.bearer,
	// },
}) {}
