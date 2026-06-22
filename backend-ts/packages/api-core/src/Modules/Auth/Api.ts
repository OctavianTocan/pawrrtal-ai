/**
 * `Authentication` — HttpApi middleware contract (api-core side).
 *
 * v4 form: `HttpApiMiddleware.Service<Authentication>()('Authentication', { provides, error, security })`.
 * The `provides: CurrentUser` declaration is what makes `yield* CurrentUser` work inside every
 * handler attached to a group that uses `.middleware(Authentication)`.
 *
 * **Status: stub.** Lesson 4 fills in `provides`, `error`, and
 * `security`; the implementation lands in `apps/api/.../Auth/Http.ts`
 * (also Lesson 4).
 *
 * v4 reference: `backend/vendor/effect-smol/ai-docs/src/51_http-server/
 * fixtures/api/Authorization.ts:16-36`.
 */

import { HttpApiMiddleware } from 'effect/unstable/httpapi';

/**
 * Auth middleware contract. The `provides: CurrentUser` declaration
 * (filled in during Lesson 4) is what makes `yield* CurrentUser` work
 * inside every handler attached to a group via `.middleware(Authentication)`.
 */
export class Authentication extends HttpApiMiddleware.Service<Authentication>()('Authentication', {
	// provides: CurrentUser,
	// error: AuthenticationError,
	// security: {
	// 	cookie: HttpApiSecurity.apiKey({ in: 'cookie', key: SESSION_COOKIE }),
	// 	bearer: HttpApiSecurity.bearer,
	// },
}) {}
