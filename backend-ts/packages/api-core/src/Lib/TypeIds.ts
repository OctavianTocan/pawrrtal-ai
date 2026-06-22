/**
 * Type IDs for project and user.
 * No random constants here, only rules for type IDs.
 */

import { Schema } from 'effect';

/**
 * UUID string schema for project and user primary keys.
 *
 * Annotated as `Schema.Codec<string>` (not `Schema.Schema<string>`): the
 * type-only `Schema<T>` view extends `Top`, whose `DecodingServices` is
 * `unknown`. That leaks into every entity built from these IDs (e.g. `User`,
 * `Project`) and surfaces wherever the schema's `DecodingServices` channel is
 * read — for example `HttpClientResponse.schemaBodyJson(User)`, whose R-channel
 * is `User["DecodingServices"]`. `Codec<string>` defaults both service channels
 * to `never`, keeping the decoded `Type` as `string` with no required services.
 */
const Uuid: Schema.Codec<string> = Schema.String.check(Schema.isUUID(4));

/**
 * ID schemas for project and user.
 * Used in path params and fields on Project and User entities.
 */
export const Ids = {
	project: Uuid,
	user: Uuid,
} as const;

/**
 * Type aliases for project and user IDs.
 */
export type ProjectId = Schema.Schema.Type<typeof Ids.project>;
export type UserId = Schema.Schema.Type<typeof Ids.user>;
