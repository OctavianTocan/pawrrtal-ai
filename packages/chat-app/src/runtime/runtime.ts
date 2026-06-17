/**
 * The singleton `ManagedRuntime` the whole app runs on.
 *
 * `ManagedRuntime` builds the {@link AppLayer} once (memoizing every service)
 * and exposes `runPromise` / `runSync` / `runFork`. React code never touches
 * `Effect.run*` directly — it goes through this runtime via the bridge hooks.
 */
import * as ManagedRuntime from 'effect/ManagedRuntime';
import { AppLayer } from './layer';

/** Process-wide runtime providing the store, catalog, and navigation. */
export const appRuntime = ManagedRuntime.make(AppLayer);

/** The concrete runtime type, used to type the React context value. */
export type AppRuntime = typeof appRuntime;
