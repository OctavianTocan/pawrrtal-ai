/**
 * React bridge for the Effect v4 runtime.
 *
 * `@effect-atom/atom-react` only supports Effect v3, so this app bridges the
 * v4 `ManagedRuntime` to React by hand: `useAppState` subscribes to the
 * store's `changes` stream through `useSyncExternalStore`, and `useRun`
 * dispatches action effects onto the runtime. Reads are synchronous via
 * `SubscriptionRef.getUnsafe`, so there is no loading flicker.
 */

import * as Effect from 'effect/Effect';
import * as Fiber from 'effect/Fiber';
import * as Stream from 'effect/Stream';
import { type ReactNode, useCallback, useSyncExternalStore } from 'react';
import { type AppState, AppStore, Catalog, type CatalogShape } from '@/services';
import type { AppServices } from './layer';
import { appRuntime } from './runtime';

/** Lazily-resolved singletons (the layer is built once by the runtime). */
let storeRef: ReturnType<typeof resolveStore> | null = null;
let catalogRef: CatalogShape | null = null;

/** Resolve the store service synchronously from the runtime. */
function resolveStore(): { getUnsafe: () => AppState; changes: Stream.Stream<AppState> } {
  return appRuntime.runSync(
    Effect.gen(function* () {
      const store = yield* AppStore;
      return { getUnsafe: store.getUnsafe, changes: store.changes };
    }),
  );
}

/** Get (and cache) the resolved store binding. */
function store(): { getUnsafe: () => AppState; changes: Stream.Stream<AppState> } {
  if (!storeRef) storeRef = resolveStore();
  return storeRef;
}

/**
 * Stable `useSyncExternalStore` subscribe: forks a fiber draining the store's
 * `changes` stream and notifies React on each emission; interrupts on cleanup.
 */
function subscribe(onChange: () => void): () => void {
  const fiber = appRuntime.runFork(Stream.runForEach(store().changes, () => Effect.sync(onChange)));
  return () => {
    appRuntime.runFork(Fiber.interrupt(fiber));
  };
}

/** Stable snapshot getter for `useSyncExternalStore`. */
function getSnapshot(): AppState {
  return store().getUnsafe();
}

/** Subscribe to the full transient UI state; re-renders on any change. */
export function useAppState(): AppState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/** Resolve the static catalog (models + conversations) once. */
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
