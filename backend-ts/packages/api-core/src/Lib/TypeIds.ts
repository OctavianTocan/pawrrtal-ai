/** UUID v4 schemas for entity primary keys. */

import { Schema } from "effect"

/** UUID v4 codec. Using `Codec` (not `Schema`) keeps `DecodingServices` at `never` for entities that use these IDs. */
const Uuid: Schema.Codec<string> = Schema.String.check(Schema.isUUID(4))

/** ID schemas. */
export const Ids = {
  /** Project ID schema. */
  project: Uuid.annotate({
    identifier: "ProjectId",
    description: "The ID of the project."
  }),
  /** User ID schema. */
  user: Uuid.annotate({
    identifier: "UserId",
    description: "The ID of the user."
  }),
  /** Conversation ID schema. */
  conversation: Uuid.annotate({
    identifier: "ConversationId",
    description: "The ID of the conversation."
  }),
  /** Chat message ID schema. */
  chatMessage: Uuid.annotate({
    identifier: "ChatMessageId",
    description: "The ID of the chat message."
  })
} as const

/** Project ID. */
export type ProjectId = Schema.Schema.Type<typeof Ids.project>
/** User ID. */
export type UserId = Schema.Schema.Type<typeof Ids.user>
/** Conversation ID. */
export type ConversationId = Schema.Schema.Type<typeof Ids.conversation>
