import { Schema } from 'effect';
import { isMaxLength, isMinLength, isTrimmed } from 'effect/Schema';
import { Ids } from '../../Lib/TypeIds';

/** Conversation title: trimmed, 1–255 characters. */
// TODO: This needs to be properly exported from somewhere logical.
export const ConversationTitle: Schema.String = Schema.String.pipe(
  Schema.check(isMinLength(1)),
  Schema.check(isMaxLength(255)),
  Schema.check(isTrimmed())
).annotate({
  identifier: 'ConversationTitle',
  description: 'The title of the conversation.'
});

/** Role of a chat message: `user` or `assistant`. */
export const ChatMessageRole = Schema.Literals(['user', 'assistant']).annotate({
  identifier: 'ChatMessageRole',
  description: 'The role of the chat message.'
});

/** A conversation groups chat messages under a single thread. */
export class Conversation extends Schema.Class<Conversation>('Conversation')({
  /** Unique identifier of the conversation. */
  id: Ids.conversation,
  /** Display title of the conversation. */
  title: ConversationTitle,
  /** The date and time the conversation was created. */
  createdAt: Schema.Date.annotate({
    description: 'The date and time the conversation was created.'
  }),
  /** The date and time the conversation was last updated. */
  updatedAt: Schema.Date.annotate({
    description: 'The date and time the conversation was last updated.'
  })
}) {}

/** Payload for creating a new conversation. */
export class ConversationCreateInput extends Schema.Class<ConversationCreateInput>('ConversationCreateInput')({
  /** Conversation id; the frontend may pre-generate the UUID. */
  id: Ids.conversation,
  /** Initial title shown before an LLM-generated title is available. */
  title: Schema.optionalKey(ConversationTitle)
}) {}

/** Payload for updating an existing conversation; omit a field to leave it unchanged. */
export class ConversationUpdateInput extends Schema.Class<ConversationUpdateInput>('ConversationUpdateInput')({
  /** New title; omit to keep the current title. */
  title: Schema.optional(ConversationTitle),
  /** New project linkage; omit to keep the current project. */
  projectId: Schema.optionalKey(Ids.project)
}) {}

/** A chat message returned to clients. */
export class ChatMessageRead extends Schema.Class<ChatMessageRead>('ChatMessageRead')({
  /** Unique identifier of the chat message. */
  id: Ids.chatMessage,
  /** Whether the message came from the user or the assistant. */
  role: ChatMessageRole,
  /** Text content of the chat message. */
  content: Schema.String.annotate({
    identifier: 'ChatMessageContent',
    description: 'The content of the chat message.'
  })
}) {}
