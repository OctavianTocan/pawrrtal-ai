import { Schema } from "effect"
import { isMaxLength, isMinLength, isTrimmed } from "effect/Schema"
import { Ids } from "../../Lib/TypeIds"

/** Conversation title: trimmed, 1–255 characters. */
const ConversationTitle: Schema.String = Schema.String.pipe(
  Schema.check(isMinLength(1)),
  Schema.check(isMaxLength(255)),
  Schema.check(isTrimmed())
).annotate({
  identifier: "ConversationTitle",
  description: "The title of the conversation."
})

/** Role of a chat message: `user` or `assistant`. */
export const ChatMessageRole = Schema.Literals(["user", "assistant"])

/** A conversation groups chat messages under a single thread. */
export class Conversation extends Schema.Class<Conversation>("Conversation")({
  /** Unique identifier of the conversation. */
  id: Ids.conversation
}) {}

/** Payload for creating a new conversation. */
export class ConversationCreateInput extends Schema.Class<ConversationCreateInput>("ConversationCreateInput")({
  /** Conversation id; the frontend may pre-generate the UUID. */
  id: Ids.conversation,
  /** Initial title shown before an LLM-generated title is available. */
  title: ConversationTitle
}) {}

/** Payload for updating an existing conversation; omit a field to leave it unchanged. */
export class ConversationUpdateInput extends Schema.Class<ConversationUpdateInput>("ConversationUpdateInput")({
  /** New title; omit to keep the current title. */
  title: Schema.optional(ConversationTitle),
  /** New project linkage; omit to keep the current project. */
  projectId: Schema.optional(Ids.project)
}) {}

/** A chat message returned to clients. */
export class ChatMessageRead extends Schema.Class<ChatMessageRead>("ChatMessageRead")({
  /** Unique identifier of the chat message. */
  id: Ids.chatMessage,
  /** Whether the message came from the user or the assistant. */
  role: ChatMessageRole,
  /** Text content of the chat message. */
  content: Schema.String.annotate({
    identifier: "ChatMessageContent",
    description: "The content of the chat message."
  })
}) {}
