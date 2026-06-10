import { HttpApiMiddleware } from 'effect/unstable/httpapi';

// Middleware is part of the contract, not the implementation.

export class Authentication extends HttpApiMiddleware.Service<Authentication>()('Authentication', {
	// provides: AuthContext,
	// failure: Schema.Union(AuthenticationError, InternalError),
	// security: {
	// 	cookie: HttpApiSecurity.apiKey({ in: 'cookie', key: SESSION_COOKIE }),
	// 	bearer: HttpApiSecurity.bearer,
	// },
}) {}
