/**
 * Type IDs for project and user.
 * No random constants here, only rules for type IDs.
 */

import { Schema } from 'effect';

/**
 * UUID string schema for project and user primary keys.
 */
const Uuid: Schema.Schema<string> = Schema.String.check(Schema.isUUID(4));

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
