import { User } from "@pawrrtal/api-core/Modules/Auth/Domain"
import { SessionStoreError } from "@pawrrtal/api-core/Modules/Auth/Errors"
import { Context, Effect, flow, Layer, Schedule } from "effect"
import { FetchHttpClient, HttpClient, HttpClientRequest, HttpClientResponse } from "effect/unstable/http"

/** Resolves a `session_token` cookie to a `User` via Python `GET /users/me`. */
export class SessionStore extends Context.Service<
  SessionStore,
  {
    readonly lookup: (cookieValue: string) => Effect.Effect<User, SessionStoreError>
  }
>()("@apps/api/Auth/SessionStore") {}

/** `SessionStore` without `HttpClient`; wire with {@link SessionStoreLive} in production. */
export const SessionStoreBody: Layer.Layer<SessionStore, never, HttpClient.HttpClient> = Layer.effect(
  SessionStore,
  Effect.gen(function* () {
    const client = (yield* HttpClient.HttpClient).pipe(
      HttpClient.mapRequest(
        flow(HttpClientRequest.prependUrl("http://localhost:8000/api/v1/"), HttpClientRequest.acceptJson)
      ),
      HttpClient.filterStatusOk,
      HttpClient.retryTransient({
        schedule: Schedule.exponential(100),
        times: 3
      })
    )

    const lookup = Effect.fn("SessionStore.lookup")(function* (cookieValue: string) {
      const user = yield* client
        .get("users/me", {
          headers: {
            Cookie: `session_token=${cookieValue}`
          }
        })
        .pipe(
          Effect.flatMap(HttpClientResponse.schemaBodyJson(User)),
          Effect.mapError(
            (cause) =>
              new SessionStoreError({
                message: "Failed to lookup user",
                cause
              })
          ),
          Effect.withSpan("SessionStore.lookup")
        )

      return user
    })

    return SessionStore.of({ lookup })
  })
)

/** Production `SessionStore` with fetch-based `HttpClient`. */
export const SessionStoreLive: Layer.Layer<SessionStore, never, never> = Layer.provide(SessionStoreBody, [
  FetchHttpClient.layer
])
