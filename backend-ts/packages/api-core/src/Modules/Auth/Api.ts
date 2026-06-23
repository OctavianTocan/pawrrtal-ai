import { HttpApiMiddleware, HttpApiSecurity } from 'effect/unstable/httpapi';
import type { CurrentUser } from './Domain';
import { AuthenticationError } from './Errors';

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
