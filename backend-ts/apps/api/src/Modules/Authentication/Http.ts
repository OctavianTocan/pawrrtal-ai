import {
	AllowedUserMiddlewareService,
	AuthenticationMiddlewareService,
} from '@pawrrtal/api-core/Modules/Auth/Api';
import { CurrentUser } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { AuthenticationError, AuthorizationError } from '@pawrrtal/api-core/Modules/Auth/Errors';
import { Effect, Layer, Redacted } from 'effect';
import { AuthenticationConfig } from './Config';
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

/** Middleware to check if the user is allowed to access the resource. */
export const AllowedUserLayer = Layer.effect(
	AllowedUserMiddlewareService,
	Effect.gen(function* () {
		yield* Effect.logInfo('Starting Allowed User middleware');
		const authenticationConfig = yield* AuthenticationConfig;
		const allowedEmails = authenticationConfig.allowedEmails;

		return AllowedUserMiddlewareService.of((httpEffect, _options) =>
			Effect.gen(function* () {
				const user = yield* CurrentUser;
				if (allowedEmails.size > 0 && !allowedEmails.has(user.email.toLowerCase())) {
					return yield* Effect.fail(
						new AuthorizationError({
							message: 'This Pawrrtal deployment is private.',
							cause: new Error('email not on allowlist'),
						})
					);
				}
				return yield* httpEffect;
			})
		);
	})
);

/** Production auth middleware with {@link SessionStoreLive}. */
export const HttpAuthLive = AuthenticationLayer.pipe(Layer.provide(SessionStoreLive));

/** Production allowed-user middleware; reads {@link AuthenticationConfig} at layer build time. */
export const HttpAllowedUserLive = AllowedUserLayer;
