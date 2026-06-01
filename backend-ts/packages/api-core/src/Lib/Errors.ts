/**
 * Cross-cutting API errors shared across HttpApi groups.
 *
 * Example (uncomment when adding the first error):
 *
 * ```ts
 * import { Schema } from "effect";
 * import { HttpApiSchema } from "effect/unstable/httpapi";
 *
 * export class InternalError extends Schema.TaggedError<InternalError>()(
 *   "InternalError",
 *   {
 *     message: Schema.String,
 *     cause: Schema.optional(Schema.Unknown),
 *   },
 *   HttpApiSchema.annotations({ status: 500 }) as { status: 500 },
 * ) {}
 * ```
 */
