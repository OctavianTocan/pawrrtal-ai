import { HttpApiMiddleware, HttpApiSecurity } from 'effect/unstable/httpapi';
import type { CurrentUser } from './Domain';
import { AuthenticationError, AuthorizationError } from './Errors';

/** Cookie auth middleware contract; runtime in `apps/api/.../Authentication/Http.ts`. */
export class AuthenticationMiddlewareService extends HttpApiMiddleware.Service<
	AuthenticationMiddlewareService,
	{
		provides: CurrentUser;
		requires: never;
	}
>()('AuthenticationMiddlewareService', {
	error: AuthenticationError,
	requiredForClient: true,
	security: {
		cookie: HttpApiSecurity.apiKey({ in: 'cookie', key: 'session_token' }),
	},
}) {}

/** Middleware to check if the user is allowed to access the resource. */
export class AllowedUserMiddlewareService extends HttpApiMiddleware.Service<
	AllowedUserMiddlewareService,
	{
		requires: CurrentUser;
		provides: never;
	}
>()('AllowedUserMiddlewareService', {
	error: AuthorizationError,
	// Nothing to send to this one.
	requiredForClient: false,
}) {}
