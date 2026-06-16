/**
 * `ConversationsStore` — the reactive list of conversations and their message
 * threads. Held in a `SubscriptionRef` so screens re-render as messages are
 * added. Sending a message appends the user's text and a local placeholder
 * assistant reply (there is no backend yet — this is a UI-only build).
 */
import * as Context from 'effect/Context';
import * as Effect from 'effect/Effect';
import * as Layer from 'effect/Layer';
import type * as Stream from 'effect/Stream';
import * as SubscriptionRef from 'effect/SubscriptionRef';
import { SEED_CONVERSATIONS } from '@/data/seed';
import type { Conversation, Message } from '@/domain';

/** Max characters of the first message used as a conversation title. */
const TITLE_MAX_CHARS = 42;

/** Build a conversation title from the opening message. */
function titleFromText(text: string): string {
  const trimmed = text.trim();
  return trimmed.length > TITLE_MAX_CHARS ? `${trimmed.slice(0, TITLE_MAX_CHARS)}…` : trimmed;
}

/** Create a user + placeholder-assistant message pair for `text`. */
function exchange(text: string): readonly [Message, Message] {
  const now = Date.now();
  const user: Message = { id: `m-${now}-u`, role: 'user', text: text.trim(), createdAt: now };
  const assistant: Message = {
    id: `m-${now}-a`,
    role: 'assistant',
    text: 'This is a UI demo — responses are not wired to a model yet.',
    createdAt: now + 1,
  };
  return [user, assistant];
}

/** Public surface of the conversations store. */
export interface ConversationsStoreShape {
  /** Read the current list once. */
  readonly list: Effect.Effect<readonly Conversation[]>;
  /** Synchronous read for `useSyncExternalStore`'s getSnapshot. */
  readonly getUnsafe: () => readonly Conversation[];
  /** Stream of the current value followed by every change. */
  readonly changes: Stream.Stream<readonly Conversation[]>;
  /** Create a new conversation seeded with the first exchange; returns its id. */
  readonly create: (text: string) => Effect.Effect<string>;
  /** Append a new exchange to an existing conversation. */
  readonly send: (conversationId: string, text: string) => Effect.Effect<void>;
}

/** Service key for the conversations store. */
export class ConversationsStore extends Context.Service<
  ConversationsStore,
  ConversationsStoreShape
>()('ChatApp/ConversationsStore') {}

/** Live layer: seeds the history list and exposes create/send mutations. */
export const ConversationsStoreLive: Layer.Layer<ConversationsStore> = Layer.effect(
  ConversationsStore,
  Effect.gen(function* () {
    const ref = yield* SubscriptionRef.make<readonly Conversation[]>(SEED_CONVERSATIONS);

    const create = (text: string): Effect.Effect<string> =>
      Effect.gen(function* () {
        const id = `c-${Date.now()}`;
        const conversation: Conversation = {
          id,
          title: titleFromText(text),
          timeLabel: 'Now',
          messages: exchange(text),
        };
        yield* SubscriptionRef.update(ref, (prev) => [conversation, ...prev]);
        return id;
      });

    const send = (conversationId: string, text: string): Effect.Effect<void> =>
      SubscriptionRef.update(ref, (prev) =>
        prev.map((conversation) =>
          conversation.id === conversationId
            ? { ...conversation, messages: [...conversation.messages, ...exchange(text)] }
            : conversation,
        ),
      );

    return ConversationsStore.of({
      list: SubscriptionRef.get(ref),
      getUnsafe: () => SubscriptionRef.getUnsafe(ref),
      changes: SubscriptionRef.changes(ref),
      create,
      send,
    });
  }),
);
