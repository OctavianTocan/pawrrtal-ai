/**
 * React bridge for the Effect v4 runtime.
 *
 * `@effect-atom/atom-react` only supports Effect v3, so this app bridges the
 * v4 `ManagedRuntime` to React by hand. `makeReactiveHook` turns any service
 * that exposes `{ getUnsafe, changes }` into a `useSyncExternalStore` hook:
 * the snapshot is read synchronously (no loading flicker) and a forked fiber
 * draining the `changes` stream notifies React on every update.
 */

import * as Effect from 'effect/Effect';
import * as Fiber from 'effect/Fiber';
import * as Stream from 'effect/Stream';
import { type ReactNode, useCallback, useSyncExternalStore } from 'react';
import type { Conversation } from '@/domain';
import {
  type AppState,
  AppStore,
  Catalog,
  type CatalogShape,
  ConversationsStore,
} from '@/services';
import type { AppServices } from './layer';
import { appRuntime } from './runtime';

/** A reactive view: a synchronous read plus a stream of changes. */
interface Reactive<A> {
  readonly getUnsafe: () => A;
  readonly changes: Stream.Stream<A>;
}

/**
 * Build a `useSyncExternalStore` hook from a function that resolves a
 * {@link Reactive} view off the runtime. The view is resolved once and cached;
 * subscribe/getSnapshot are stable module-level closures.
 */
function makeReactiveHook<A>(resolve: () => Reactive<A>): () => A {
  let view: Reactive<A> | null = null;
  const get = (): Reactive<A> => {
    if (!view) view = resolve();
    return view;
  };
  const subscribe = (onChange: () => void): (() => void) => {
    const fiber = appRuntime.runFork(Stream.runForEach(get().changes, () => Effect.sync(onChange)));
    return () => {
      appRuntime.runFork(Fiber.interrupt(fiber));
    };
  };
  const getSnapshot = (): A => get().getUnsafe();
  return () => useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/** Subscribe to the transient UI state (home mode, tier, overlay). */
export const useAppState = makeReactiveHook<AppState>(() =>
  appRuntime.runSync(
    Effect.gen(function* () {
      const store = yield* AppStore;
      return { getUnsafe: store.getUnsafe, changes: store.changes };
    }),
  ),
);

/** Subscribe to the conversation history + threads. */
export const useConversations = makeReactiveHook<readonly Conversation[]>(() =>
  appRuntime.runSync(
    Effect.gen(function* () {
      const store = yield* ConversationsStore;
      return { getUnsafe: store.getUnsafe, changes: store.changes };
    }),
  ),
);

/** Resolve the static catalog (models) once. */
let catalogRef: CatalogShape | null = null;
export function useCatalog(): CatalogShape {
  if (!catalogRef) {
    catalogRef = appRuntime.runSync(
      Effect.gen(function* () {
        return yield* Catalog;
      }),
    );
  }
  return catalogRef;
}

/**
 * Returns a dispatcher that runs an action effect on the app runtime
 * (fire-and-forget). The effect's requirements are satisfied by the runtime's
 * layer, so callers only pass effects built from {@link actions}.
 */
export function useRun(): (effect: Effect.Effect<void, never, AppServices>) => void {
  return useCallback((effect) => {
    appRuntime.runFork(effect);
  }, []);
}

/**
 * Root provider. The runtime is a process-wide singleton, so this is a thin
 * pass-through today; it exists as the documented seam for runtime scoping if
 * the app later needs per-tree runtimes.
 */
export function RuntimeProvider({ children }: { readonly children: ReactNode }): ReactNode {
  return children;
}
