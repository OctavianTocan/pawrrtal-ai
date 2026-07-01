import type { ConversationId, UserId } from "@pawrrtal/api-core/Lib/TypeIds"
import type {
  ChatMessageRead,
  Conversation,
  ConversationCreateInput,
  ConversationUpdateInput
} from "@pawrrtal/api-core/Modules/Conversations/Domain"
import type {
  ConversationAlreadyExistsError,
  ConversationNotFoundError
} from "@pawrrtal/api-core/Modules/Conversations/Errors"
import { Context, Effect, Layer } from "effect"
import { ConversationsRepo } from "./Repo"

/** Conversation CRUD business rules; callers pass the authenticated `userId`. */
export class ConversationsService extends Context.Service<
  ConversationsService,
  {
    readonly list: (userId: UserId) => Effect.Effect<ReadonlyArray<Conversation>>
    readonly create: (
      userId: UserId,
      payload: ConversationCreateInput
    ) => Effect.Effect<Conversation, ConversationAlreadyExistsError>
    readonly get: (
      userId: UserId,
      conversationId: ConversationId
    ) => Effect.Effect<Conversation, ConversationNotFoundError>
    readonly update: (
      userId: UserId,
      conversationId: ConversationId,
      payload: ConversationUpdateInput
    ) => Effect.Effect<Conversation, ConversationNotFoundError>
    readonly delete: (userId: UserId, conversationId: ConversationId) => Effect.Effect<void, ConversationNotFoundError>
    readonly getMessages: (
      userId: UserId,
      conversationId: ConversationId
    ) => Effect.Effect<ReadonlyArray<ChatMessageRead>, ConversationNotFoundError>
  }
>()("@apps/api/Conversations/Service") {}

/** `ConversationsService` without `ConversationsRepo`; wire with a live repo layer when implemented. */
export const ConversationsServiceBody: Layer.Layer<ConversationsService, never, ConversationsRepo> = Layer.effect(
  ConversationsService,
  Effect.gen(function* () {
    const repo = yield* ConversationsRepo

    const listConversations = Effect.fn("ConversationsService.list")((userId: UserId) => repo.list(userId))
    const createConversation = Effect.fn("ConversationsService.create")(
      (userId: UserId, payload: ConversationCreateInput) => repo.create(userId, payload)
    )
    const getConversation = Effect.fn("ConversationsService.get")((userId: UserId, conversationId: ConversationId) =>
      repo.get(userId, conversationId)
    )
    const updateConversation = Effect.fn("ConversationsService.update")(
      (userId: UserId, conversationId: ConversationId, payload: ConversationUpdateInput) =>
        repo.update(userId, conversationId, payload)
    )
    const deleteConversation = Effect.fn("ConversationsService.delete")(
      (userId: UserId, conversationId: ConversationId) => repo.delete(userId, conversationId)
    )
    const getConversationMessages = Effect.fn("ConversationsService.getMessages")(
      (userId: UserId, conversationId: ConversationId) => repo.getMessages(userId, conversationId)
    )

    return {
      list: listConversations,
      create: createConversation,
      get: getConversation,
      update: updateConversation,
      delete: deleteConversation,
      getMessages: getConversationMessages
    } as const
  })
)
