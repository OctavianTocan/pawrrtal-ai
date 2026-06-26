/** UUID v4 schemas for project and user primary keys. */

import { Schema } from "effect"

// Codec (not Schema) keeps DecodingServices at `never` for entities that use these IDs.
const Uuid: Schema.Codec<string> = Schema.String.check(Schema.isUUID(4))

export const Ids = {
  project: Uuid,
  user: Uuid
} as const

export type ProjectId = Schema.Schema.Type<typeof Ids.project>
export type UserId = Schema.Schema.Type<typeof Ids.user>
