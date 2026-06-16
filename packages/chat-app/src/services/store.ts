/**
 * `AppStore` — the single Effect-managed source of truth for transient UI
 * state (home mode, selected model tier, composer text, which overlay is
 * open, voice-capture state).
 *
 * State lives in a `SubscriptionRef`, so React can subscribe to `changes`
 * (a `Stream`) and read the latest value synchronously via `getUnsafe`. Every
 * mutation is an `Effect`, keeping all state transitions inside the runtime.
 */
import * as Context from 'effect/Context';
import * as Effect from 'effect/Effect';
import * as Layer from 'effect/Layer';
import type * as Stream from 'effect/Stream';
import * as SubscriptionRef from 'effect/SubscriptionRef';
import { DEFAULT_MODEL_TIER } from '@/data/seed';
import type { HomeMode, ModelTier } from '@/domain';

/** Which transient overlay (if any) is currently presented over the home screen. */
export type Overlay = 'none' | 'model' | 'attachment' | 'voice';

/** The full transient UI state held by the store. */
export interface AppState {
  /** Active home tab. */
  readonly homeMode: HomeMode;
  /** Currently selected reasoning tier. */
  readonly selectedTier: ModelTier;
  /** Draft text in the composer. */
  readonly composerText: string;
  /** Which overlay is open over the home canvas. */
  readonly overlay: Overlay;
}

/** Initial state on a cold start. */
const INITIAL_STATE: AppState = {
  homeMode: 'ask',
  selectedTier: DEFAULT_MODEL_TIER,
  composerText: '',
  overlay: 'none',
};

/** Public surface of the store service. */
export interface AppStoreShape {
  /** Read the current state once. */
  readonly state: Effect.Effect<AppState>;
  /** Synchronous read for `useSyncExternalStore`'s getSnapshot. */
  readonly getUnsafe: () => AppState;
  /** Stream of the current value followed by every subsequent change. */
  readonly changes: Stream.Stream<AppState>;
  /** Switch the active home tab. */
  readonly setHomeMode: (mode: HomeMode) => Effect.Effect<void>;
  /** Select a reasoning tier and close the model overlay. */
  readonly selectTier: (tier: ModelTier) => Effect.Effect<void>;
  /** Update the composer draft text. */
  readonly setComposerText: (text: string) => Effect.Effect<void>;
  /** Present (or dismiss) an overlay. */
  readonly setOverlay: (overlay: Overlay) => Effect.Effect<void>;
}

/**
 * Service key for the app store. Yielding it in an `Effect` adds `AppStore`
 * to the requirement set and resolves to {@link AppStoreShape}.
 */
export class AppStore extends Context.Service<AppStore, AppStoreShape>()('ChatApp/AppStore') {}

/** Live layer: builds the `SubscriptionRef` and the mutation closures over it. */
export const AppStoreLive: Layer.Layer<AppStore> = Layer.effect(
  AppStore,
  Effect.gen(function* () {
    const ref = yield* SubscriptionRef.make(INITIAL_STATE);
    const patch = (next: Partial<AppState>): Effect.Effect<void> =>
      SubscriptionRef.update(ref, (prev) => ({ ...prev, ...next }));

    return AppStore.of({
      state: SubscriptionRef.get(ref),
      getUnsafe: () => SubscriptionRef.getUnsafe(ref),
      changes: SubscriptionRef.changes(ref),
      setHomeMode: (homeMode) => patch({ homeMode }),
      selectTier: (selectedTier) => patch({ selectedTier, overlay: 'none' }),
      setComposerText: (composerText) => patch({ composerText }),
      setOverlay: (overlay) => patch({ overlay }),
    });
  }),
);
