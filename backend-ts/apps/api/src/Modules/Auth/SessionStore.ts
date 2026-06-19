import { User } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { SessionStoreError } from '@pawrrtal/api-core/Modules/Auth/Errors';
import { Context, Effect, flow, Layer, Schedule } from 'effect';
import {
	FetchHttpClient,
	HttpClient,
	HttpClientRequest,
	HttpClientResponse,
} from 'effect/unstable/http';

/**
 * The session store is responsible for resolving a session cookie value to a typed User by making an HTTP call to the Python backend API.
 */
export class SessionStore extends Context.Service<
	SessionStore,
	{
		/** Returns the user corresponding to the given cookie value, if one exists. */
		readonly lookup: (cookieValue: string) => Effect.Effect<User, SessionStoreError>;
	}
>()('@apps/api/Auth/SessionStore') {}

/**
 * SessionStore implementation layer with no concrete `HttpClient` implementation attached.
 * Resolves session tokens via the provided `HttpClient`. Wired in production by {@link SessionStoreLive}
 * and can be overridden in tests.
 */
export const SessionStoreBody: Layer.Layer<SessionStore, never, HttpClient.HttpClient> =
	Layer.effect(
		SessionStore,
		Effect.gen(function* () {
			// Access the HttpClient service, and apply some common middleware to all
			// requests:
			const client = (yield* HttpClient.HttpClient).pipe(
				// Add a base URL to all requests made with this client, and set the
				// Accept header to expect JSON responses
				HttpClient.mapRequest(
					flow(
						HttpClientRequest.prependUrl('http://localhost:8000/api/v1/'),
						HttpClientRequest.acceptJson
					)
				),
				// Fail if the response status is not 2xx
				HttpClient.filterStatusOk,
				// Retry transient errors (network issues, 5xx responses) with an
				// exponential backoff.
				//
				// See the schedule documentation for more complex retry strategies.
				HttpClient.retryTransient({
					schedule: Schedule.exponential(100),
					times: 3,
				})
			);

			/** Lookup the user corresponding to the given cookie value. */
			const lookup = Effect.fn('SessionStore.lookup')(function* (cookieValue: string) {
				const user = yield* client
					.get('users/me', {
						headers: {
							Cookie: `session_token=${cookieValue}`,
						},
					})
					.pipe(
						Effect.flatMap(HttpClientResponse.schemaBodyJson(User)),
						Effect.mapError(
							(cause) =>
								new SessionStoreError({
									message: 'Failed to lookup user',
									cause,
								})
						),
						Effect.withSpan('SessionStore.lookup')
					);
				return user;
			});

			return SessionStore.of({ lookup });
		})
	);

/**
 * Production SessionStore layer. Provides {@link SessionStore} with the default fetch-based HTTP client implementation.
 */
export const SessionStoreLive: Layer.Layer<SessionStore, never, never> = Layer.provide(
	SessionStoreBody,
	[FetchHttpClient.layer]
);
