import { Schema } from 'effect';

/** Session store lookup failure. */
export class SessionStoreError extends Schema.TaggedErrorClass<SessionStoreError>()(
	'SessionStoreError',
	{
		message: Schema.String,
		cause: Schema.Defect,
	}
) {}

/** Missing or invalid session (HTTP 401). */
export class AuthenticationError extends Schema.TaggedErrorClass<AuthenticationError>()(
	'AuthenticationError',
	{
		message: Schema.String,
		cause: Schema.Defect,
	},
	{
		httpApiStatus: 401,
	}
) {}
