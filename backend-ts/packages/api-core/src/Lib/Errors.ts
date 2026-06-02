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
