/**
 * Cross-cutting API errors shared by every HttpApi group.
 *
 * Module-specific errors live in each `Modules/<Name>/Errors.ts` next
 * to the group that raises them. Add a class here only when the error
 * is genuinely cross-module (e.g. a generic 500 fallback).
 */

import { Schema } from 'effect';

/**
 * Internal error. Used when an unexpected error occurs.
 */
export class InternalError extends Schema.TaggedErrorClass<InternalError>()(
	'InternalError',
	{
		message: Schema.String,
		cause: Schema.optional(Schema.Unknown),
	},
	{ httpApiStatus: 500 }
) {}
