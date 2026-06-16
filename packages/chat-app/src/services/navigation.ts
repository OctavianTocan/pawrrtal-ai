/**
 * `Navigation` — an Effect facade over `expo-router`'s imperative `router`.
 *
 * Routing this way keeps navigation as just another effect the runtime runs,
 * so screens dispatch navigation through the same `runAction` path as state
 * mutations rather than calling the router directly.
 */

import * as Context from 'effect/Context';
import * as Effect from 'effect/Effect';
import * as Layer from 'effect/Layer';
import { router } from 'expo-router';

/** Public surface of the navigation service. */
export interface NavigationShape {
  /** Push a new route onto the stack. */
  readonly push: (href: string) => Effect.Effect<void>;
  /** Replace the current route. */
  readonly replace: (href: string) => Effect.Effect<void>;
  /** Pop back to the previous route. */
  readonly back: Effect.Effect<void>;
}

/** Service key for navigation. */
export class Navigation extends Context.Service<Navigation, NavigationShape>()(
  'ChatApp/Navigation',
) {}

/** Live layer wrapping the `expo-router` imperative API in synchronous effects. */
export const NavigationLive: Layer.Layer<Navigation> = Layer.succeed(
  Navigation,
  Navigation.of({
    push: (href) => Effect.sync(() => router.push(href)),
    replace: (href) => Effect.sync(() => router.replace(href)),
    back: Effect.sync(() => router.back()),
  }),
);
