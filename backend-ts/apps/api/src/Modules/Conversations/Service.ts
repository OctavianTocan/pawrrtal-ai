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
import { ConversationsRepo, ConversationsRepoLive } from "./Repo"

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
    readonly remove: (userId: UserId, conversationId: ConversationId) => Effect.Effect<void, ConversationNotFoundError>
    readonly getMessages: (
      userId: UserId,
      conversationId: ConversationId
    ) => Effect.Effect<ReadonlyArray<ChatMessageRead>, ConversationNotFoundError>
  }
>()("@apps/api/Conversations/Service") {}

/** `ConversationsService` without `ConversationsRepo`; wire with {@link ConversationsServiceLive} or a test repo. */
export const ConversationsServiceBody: Layer.Layer<ConversationsService, never, ConversationsRepo> = Layer.effect(
  ConversationsService,
  Effect.gen(function* () {
    const repo = yield* ConversationsRepo

    const list = Effect.fn("ConversationsService.list")((userId: UserId) => repo.list(userId))
    const create = Effect.fn("ConversationsService.create")((userId: UserId, payload: ConversationCreateInput) =>
      repo.create(userId, payload)
    )
    const get = Effect.fn("ConversationsService.get")((userId: UserId, conversationId: ConversationId) =>
      repo.get(userId, conversationId)
    )
    const update = Effect.fn("ConversationsService.update")(
      (userId: UserId, conversationId: ConversationId, payload: ConversationUpdateInput) =>
        repo.update(userId, conversationId, payload)
    )
    const remove = Effect.fn("ConversationsService.remove")((userId: UserId, conversationId: ConversationId) =>
      repo.remove(userId, conversationId)
    )
    const getMessages = Effect.fn("ConversationsService.getMessages")(
      (userId: UserId, conversationId: ConversationId) => repo.getMessages(userId, conversationId)
    )

    return {
      list: list,
      create: create,
      get: get,
      update: update,
      remove: remove,
      getMessages: getMessages
    } as const
  })
)

/** Production `ConversationsService` with file-backed {@link ConversationsRepoLive}. */
export const ConversationsServiceLive: Layer.Layer<ConversationsService, never, never> = Layer.provide(
  ConversationsServiceBody,
  [ConversationsRepoLive]
)
