import { Schema } from 'effect';

/** Unexpected server failure (HTTP 500). */
export class InternalError extends Schema.TaggedErrorClass<InternalError>()(
	'InternalError',
	{
		message: Schema.String,
		cause: Schema.optional(Schema.Unknown),
	},
	{ httpApiStatus: 500 }
) {}
