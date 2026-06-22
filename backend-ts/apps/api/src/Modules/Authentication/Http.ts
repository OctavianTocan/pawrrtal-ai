import { AuthenticationMiddlewareService } from '@pawrrtal/api-core/Modules/Auth/Api';
import { CurrentUser } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { AuthenticationError } from '@pawrrtal/api-core/Modules/Auth/Errors';
import { Effect, Layer, Redacted } from 'effect';
import { SessionStore } from './SessionStore';

// What is the AuthenticationLayer?
// It is an Effect layer that implements the Authentication middleware service at runtime.

// What is it supposed to do?
// - It

// How does Authentication.of({}) work?

export const AuthenticationLayer = Layer.effect(
	AuthenticationMiddlewareService,
	Effect.gen(function* () {
		// Here you could access services required by the middleware, like a
		// database or an external auth provider.
		yield* Effect.logInfo('Starting Authorization middleware');
		const sessionStore = yield* SessionStore;

		return AuthenticationMiddlewareService.of({
			cookie: Effect.fn(function* (httpEffect, { credential }) {
				const cookie = Redacted.value(credential);
				const user = yield* sessionStore.lookup(cookie).pipe(
					Effect.mapError(
						(cause) =>
							new AuthenticationError({
								message: 'Missing or invalid session token',
								cause,
							})
					)
				);
				return yield* Effect.provideService(httpEffect, CurrentUser, user);
			}),
		});
	})
);
