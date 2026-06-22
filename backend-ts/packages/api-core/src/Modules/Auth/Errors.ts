/**
 * Authentication module — typed errors raised by the auth middleware
 * and consumed by the HTTP layer for status mapping.
 *
 * **Status: `SessionStoreError` shipped (Lesson 2).** Lesson 4
 * introduces `AuthenticationError` (with `{ httpApiStatus: 401 }`).
 * `AuthorizationError` (403) is out of scope for this arc.
 */

import { Schema } from 'effect';

/** Error raised when the session store fails. */
export class SessionStoreError extends Schema.TaggedErrorClass<SessionStoreError>()(
	'SessionStoreError',
	{
		message: Schema.String,
		cause: Schema.Defect,
	}
) {}

/** Error raised when the authentication fails. */
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
