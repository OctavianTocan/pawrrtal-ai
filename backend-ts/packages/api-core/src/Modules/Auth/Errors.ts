/**
 * Authentication module — typed errors raised by the auth middleware
 * and consumed by the HTTP layer for status mapping.
 *
 * **Status: empty.** Lesson 3 introduces `AuthenticationError` (with
 * `{ httpApiStatus: 401 }`) and possibly `AuthorizationError` (with
 * `{ httpApiStatus: 403 }`). Until then, callers should treat the file
 * as intentionally blank.
 */

import { Schema } from 'effect';

/** Error raised when the session store fails to lookup a user. */
export class SessionStoreError extends Schema.TaggedErrorClass<SessionStoreError>()(
	'SessionStoreError',
	{
		message: Schema.String,
		cause: Schema.Defect,
	}
) {}
