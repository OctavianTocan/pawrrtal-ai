import { Schema } from 'effect';
import { Ids } from '../../Lib/TypeIds';

/** Conversation missing or not owned by the requester (HTTP 404). */
export class ConversationNotFoundError extends Schema.TaggedErrorClass<ConversationNotFoundError>()(
  'ConversationNotFoundError',
  {
    detail: Schema.optional(Schema.String),
    conversation_id: Schema.optional(Ids.conversation)
  },
  { httpApiStatus: 404 }
) {}

/** Conversation already exists for the user (HTTP 409). */
export class ConversationAlreadyExistsError extends Schema.TaggedErrorClass<ConversationAlreadyExistsError>()(
  'ConversationAlreadyExistsError',
  {
    detail: Schema.optional(Schema.String),
    conversation_id: Schema.optional(Ids.conversation)
  },
  { httpApiStatus: 409 }
) {}
