import type { ConversationId, UserId } from "@pawrrtal/api-core/Lib/TypeIds"
import type {
  ChatMessageRead,
  Conversation,
  ConversationCreateInput,
  ConversationUpdateInput
} from "@pawrrtal/api-core/Modules/Conversations/Domain"
import type { Effect } from "effect"
import { Context } from "effect"

export class ConversationsRepo extends Context.Service<
  ConversationsRepo,
  {
    readonly list: (userId: UserId) => Effect.Effect<ReadonlyArray<Conversation>>
    readonly create: (userId: UserId, payload: ConversationCreateInput) => Effect.Effect<Conversation>
    readonly get: (userId: UserId, conversationId: ConversationId) => Effect.Effect<Conversation>
    readonly update: (
      userId: UserId,
      conversationId: ConversationId,
      payload: ConversationUpdateInput
    ) => Effect.Effect<Conversation>
    readonly delete: (userId: UserId, conversationId: ConversationId) => Effect.Effect<void>
    readonly getMessages: (
      userId: UserId,
      conversationId: ConversationId
    ) => Effect.Effect<ReadonlyArray<ChatMessageRead>>
  }
>()("@apps/api/Conversations/Repo") {}
