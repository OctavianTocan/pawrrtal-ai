import { AuthenticationMiddlewareService } from '@pawrrtal/api-core/Modules/Auth/Api';
import { CurrentUser } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { AuthenticationError } from '@pawrrtal/api-core/Modules/Auth/Errors';
import { Effect, Layer, Redacted } from 'effect';
import { SessionStore, SessionStoreLive } from './SessionStore';

/** Auth middleware: cookie → {@link SessionStore} → inject {@link CurrentUser}. */
export const AuthenticationLayer = Layer.effect(
	AuthenticationMiddlewareService,
	Effect.gen(function* () {
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

/** Production auth middleware with {@link SessionStoreLive}. */
export const HttpAuthLive = AuthenticationLayer.pipe(Layer.provide(SessionStoreLive));
