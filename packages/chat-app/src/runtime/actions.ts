/**
 * Action builders — small `Effect`s that resolve a service and invoke one of
 * its mutations. Components dispatch these through `useRun()` so every state
 * transition and navigation runs on the app runtime.
 */
import * as Effect from 'effect/Effect';
import type { HomeMode, ModelTier } from '@/domain';
import { AppStore, ConversationsStore, Navigation, type Overlay } from '@/services';

/** Switch the active home tab. */
export const setHomeMode = (mode: HomeMode): Effect.Effect<void, never, AppStore> =>
  Effect.gen(function* () {
    const store = yield* AppStore;
    yield* store.setHomeMode(mode);
  });

/** Select a reasoning tier (also closes the model overlay). */
export const selectTier = (tier: ModelTier): Effect.Effect<void, never, AppStore> =>
  Effect.gen(function* () {
    const store = yield* AppStore;
    yield* store.selectTier(tier);
  });

/** Present or dismiss an overlay over the home canvas. */
export const setOverlay = (overlay: Overlay): Effect.Effect<void, never, AppStore> =>
  Effect.gen(function* () {
    const store = yield* AppStore;
    yield* store.setOverlay(overlay);
  });

/** Navigate by pushing a route. */
export const navigatePush = (href: string): Effect.Effect<void, never, Navigation> =>
  Effect.gen(function* () {
    const navigation = yield* Navigation;
    yield* navigation.push(href);
  });

/** Navigate back to the previous route. */
export const navigateBack: Effect.Effect<void, never, Navigation> = Effect.gen(function* () {
  const navigation = yield* Navigation;
  yield* navigation.back;
});

/** Create a conversation from the composer text and open its thread. */
export const createConversation = (
  text: string,
): Effect.Effect<void, never, ConversationsStore | Navigation> =>
  Effect.gen(function* () {
    const store = yield* ConversationsStore;
    const id = yield* store.create(text);
    const navigation = yield* Navigation;
    yield* navigation.push(`/conversation/${id}`);
  });

/** Append a message to an existing conversation thread. */
export const sendMessage = (
  conversationId: string,
  text: string,
): Effect.Effect<void, never, ConversationsStore> =>
  Effect.gen(function* () {
    const store = yield* ConversationsStore;
    yield* store.send(conversationId, text);
  });

/** Open an existing conversation's thread. */
export const openConversation = (conversationId: string): Effect.Effect<void, never, Navigation> =>
  Effect.gen(function* () {
    const navigation = yield* Navigation;
    yield* navigation.push(`/conversation/${conversationId}`);
  });
