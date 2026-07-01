import { Schema } from "effect"

/** Session store lookup failure. */
export class SessionStoreError extends Schema.TaggedErrorClass<SessionStoreError>()("SessionStoreError", {
  message: Schema.String,
  cause: Schema.Unknown
}) {}

/** Missing or invalid session (HTTP 401). */
export class AuthenticationError extends Schema.TaggedErrorClass<AuthenticationError>()(
  "AuthenticationError",
  {
    message: Schema.String,
    cause: Schema.Unknown
  },
  {
    httpApiStatus: 401
  }
) {}

/** Authorization failure (HTTP 403). */
export class AuthorizationError extends Schema.TaggedErrorClass<AuthorizationError>()(
  "AuthorizationError",
  {
    message: Schema.String,
    cause: Schema.Unknown
  },
  {
    httpApiStatus: 403
  }
) {}
