import { User } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { Context, Effect, Layer, type Schema } from 'effect';
import { HttpClientResponse } from 'effect/unstable/http';
import * as FetchHttpClient from 'effect/unstable/http/FetchHttpClient';
import { HttpClient } from 'effect/unstable/http/HttpClient';
import type * as HttpClientError from 'effect/unstable/http/HttpClientError';

/**
 * The session store is responsible for resolving a session cookie value to a typed User by making an HTTP call to the Python backend API.
 */
export class SessionStore extends Context.Service<
    SessionStore,
    {
        /** Returns the user corresponding to the given cookie value, if one exists. */
        readonly lookup: (
            cookieValue: string
        ) => Effect.Effect<User, HttpClientError.HttpClientError | Schema.SchemaError>;
    }
>()('@apps/api/Auth/SessionStore') { }

/**
 * SessionStore implementation layer with no concrete `HttpClient` implementation attached.
 * Resolves session tokens via the provided `HttpClient`. Wired in production by {@link SessionStoreLive}
 * and can be overridden in tests.
 */
export const SessionStoreBody: Layer.Layer<SessionStore, never, HttpClient> = Layer.effect(
    SessionStore,
    Effect.gen(function* () {
        const httpClient = yield* HttpClient;
        const lookup = Effect.fn('SessionStore.lookup')(function* (cookieValue: string) {
            const response = yield* httpClient
                .get('http://localhost:8000/api/v1/users/me', {
                    headers: {
                        Cookie: `session_token=${cookieValue}`,
                    },
                })
                .pipe(Effect.flatMap(HttpClientResponse.filterStatusOk));

            const user = yield* HttpClientResponse.schemaBodyJson(User)(response);
            return user;
        }) as (
            cookieValue: string
        ) => Effect.Effect<User, HttpClientError.HttpClientError | Schema.SchemaError>;

        return {
            lookup,
        } as const;
    })
);

/**
 * Production SessionStore layer. Provides {@link SessionStore} with the default fetch-based HTTP client implementation.
 */
export const SessionStoreLive: Layer.Layer<SessionStore, never, never> = Layer.provide(
    SessionStoreBody,
    [FetchHttpClient.layer]
) as Layer.Layer<SessionStore, never, never>;
