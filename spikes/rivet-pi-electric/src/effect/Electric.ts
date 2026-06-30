/**
 * The Electric read-path client wrapped as an Effect v4 service (M7).
 *
 * The raw client is `openConversationShape` (an `@electric-sql/client`
 * ShapeStream). `awaitRow` exposes it as an effect that opens a shape, resolves
 * once the row materializes, and ALWAYS closes the stream via
 * `Effect.acquireUseRelease` — so a subscription can't leak even on timeout.
 */
import { Context, Effect, Layer } from 'effect';
import { type ConversationRow, openConversationShape } from '../shape-client.ts';

const DEFAULT_TIMEOUT_MS = 20000;

export class Electric extends Context.Service<
  Electric,
  {
    readonly awaitRow: (id: string, opts?: { where?: string; timeoutMs?: number }) => Effect.Effect<ConversationRow>;
  }
>()('@spike/effect/Electric') {}

/** A `Electric` that subscribes directly to the Electric sync service. */
export const ElectricLive: Layer.Layer<Electric> = Layer.succeed(Electric, {
  awaitRow: (id, opts = {}) =>
    Effect.acquireUseRelease(
      Effect.sync(() => openConversationShape(opts.where ? { where: opts.where } : {})),
      (shape) =>
        Effect.tryPromise(() =>
          shape
            .waitFor((rows) => rows.has(id), opts.timeoutMs ?? DEFAULT_TIMEOUT_MS)
            .then(() => {
              const row = shape.rows.get(id);
              if (!row) {
                throw new Error(`row ${id} missing after waitFor`);
              }
              return row;
            })
        ).pipe(Effect.orDie),
      (shape) => Effect.sync(() => shape.close())
    ),
});
