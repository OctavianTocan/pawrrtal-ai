import type { ChatMessageId, ConversationId, UserId } from '@pawrrtal/api-core/Lib/TypeIds';
import type { ConversationCreateInput, ConversationUpdateInput } from '@pawrrtal/api-core/Modules/Conversations/Domain';
import { ChatMessageRead, Conversation } from '@pawrrtal/api-core/Modules/Conversations/Domain';
import { Context, DateTime, Effect, Layer } from 'effect';
import { SqlClient } from 'effect/unstable/sql';
import { DatabaseLive } from '@/Infrastructure/Database';

/** Maps a SQL row to a `Conversation` instance. */
const decodeConversation = (row: Record<string, unknown>): Conversation =>
  new Conversation({
    id: row.id as ConversationId,
    title: row.title as string,
    createdAt: new Date(row.created_at as string),
    updatedAt: new Date(row.updated_at as string)
  });

/** Maps SQL rows to `Conversation` instances. */
const decodeConversations = (rows: ReadonlyArray<Record<string, unknown>>): ReadonlyArray<Conversation> =>
  rows.map(decodeConversation);

/** Maps a SQL row to a `ChatMessageRead` instance. */
const decodeChatMessage = (row: Record<string, unknown>): ChatMessageRead =>
  new ChatMessageRead({
    id: row.id as ChatMessageId,
    role: row.role as 'user' | 'assistant',
    content: row.content as string
  });

/** Maps SQL rows to `ChatMessageRead` instances. */
const decodeChatMessages = (rows: ReadonlyArray<Record<string, unknown>>): ReadonlyArray<ChatMessageRead> =>
  rows.map(decodeChatMessage);

/** SQLite persistence for conversations and messages scoped by user. */
export class ConversationsRepo extends Context.Service<
  ConversationsRepo,
  {
    readonly list: (userId: UserId) => Effect.Effect<ReadonlyArray<Conversation>>;
    readonly create: (userId: UserId, payload: ConversationCreateInput) => Effect.Effect<Conversation>;
    readonly get: (userId: UserId, conversationId: ConversationId) => Effect.Effect<Conversation>;
    readonly update: (
      userId: UserId,
      conversationId: ConversationId,
      payload: ConversationUpdateInput
    ) => Effect.Effect<Conversation>;
    readonly remove: (userId: UserId, conversationId: ConversationId) => Effect.Effect<void>;
    readonly getMessages: (
      userId: UserId,
      conversationId: ConversationId
    ) => Effect.Effect<ReadonlyArray<ChatMessageRead>>;
  }
>()('@apps/api/Conversations/Repo') {}

/** `ConversationsRepo` without `SqlClient`; wire with {@link ConversationsRepoLive} or a test DB layer. */
export const ConversationsRepoBody: Layer.Layer<ConversationsRepo, never, SqlClient.SqlClient> = Layer.effect(
  ConversationsRepo,
  Effect.gen(function* () {
    const sql = yield* SqlClient.SqlClient;

    /** List conversations for a user. */
    const list = Effect.fn('ConversationsRepo.list')(function* (userId: UserId) {
      const rows = yield* sql`SELECT id FROM conversations WHERE user_id = ${userId} ORDER BY created_at ASC`.pipe(
        Effect.orDie
      );
      return decodeConversations(rows as ReadonlyArray<Record<string, unknown>>);
    });

    /** Create a new conversation. */
    const create = Effect.fn('ConversationsRepo.create')(function* (userId: UserId, payload: ConversationCreateInput) {
      const now = yield* DateTime.now;
      const ts = DateTime.formatIso(now);

      yield* sql`INSERT INTO conversations (id, user_id, title, created_at, updated_at) VALUES (${payload.id}, ${userId}, ${payload.title}, ${ts}, ${ts})`.raw.pipe(
        sql.withTransaction,
        Effect.orDie
      );

      const rows = yield* sql`SELECT id FROM conversations WHERE id = ${payload.id}`.pipe(Effect.orDie);
      return decodeConversation(rows[0] as Record<string, unknown>);
    });

    /** Get a conversation by ID. */
    const get = Effect.fn('ConversationsRepo.get')(function* (userId: UserId, conversationId: ConversationId) {
      const rows = yield* sql`SELECT id FROM conversations WHERE id = ${conversationId} AND user_id = ${userId}`.pipe(
        Effect.orDie
      );
      return decodeConversation(rows[0] as Record<string, unknown>);
    });

    /** Update a conversation. */
    const update = Effect.fn('ConversationsRepo.update')(function* (
      userId: UserId,
      conversationId: ConversationId,
      payload: ConversationUpdateInput
    ) {
      const now = yield* DateTime.now;
      const ts = DateTime.formatIso(now);

      if (payload.title !== undefined) {
        yield* sql`UPDATE conversations SET title = ${payload.title}, updated_at = ${ts} WHERE id = ${conversationId} AND user_id = ${userId}`.pipe(
          Effect.orDie
        );
      }

      if (payload.projectId !== undefined) {
        yield* sql`UPDATE conversations SET project_id = ${payload.projectId}, updated_at = ${ts} WHERE id = ${conversationId} AND user_id = ${userId}`.pipe(
          Effect.orDie
        );
      }

      const rows = yield* sql`SELECT id FROM conversations WHERE id = ${conversationId} AND user_id = ${userId}`.pipe(
        Effect.orDie
      );
      return decodeConversation(rows[0] as Record<string, unknown>);
    });

    /** Remove a conversation. */
    const remove = Effect.fn('ConversationsRepo.delete')(function* (userId: UserId, conversationId: ConversationId) {
      yield* sql`DELETE FROM conversations WHERE id = ${conversationId} AND user_id = ${userId}`.pipe(Effect.orDie);
    });

    /** Get messages for a conversation. */
    const getMessages = Effect.fn('ConversationsRepo.getMessages')(function* (
      userId: UserId,
      conversationId: ConversationId
    ) {
      const rows =
        yield* sql`SELECT m.id, m.role, m.content FROM chat_messages m INNER JOIN conversations c ON c.id = m.conversation_id WHERE c.id = ${conversationId} AND c.user_id = ${userId} ORDER BY m.ordinal ASC`.pipe(
          Effect.orDie
        );
      return decodeChatMessages(rows as ReadonlyArray<Record<string, unknown>>);
    });

    return { list, create, get, update, remove: remove, getMessages } as const;
  })
);

/** Production `ConversationsRepo` backed by file SQLite. */
export const ConversationsRepoLive: Layer.Layer<ConversationsRepo, never, never> = Layer.provide(
  ConversationsRepoBody,
  [DatabaseLive]
) as Layer.Layer<ConversationsRepo, never, never>;
