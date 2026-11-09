/**
 * The Postgres pool wrapped as an Effect v4 service (M7).
 *
 * The raw client is node-postgres' `Pool` (the same one `db.ts` uses). Here it
 * is acquired/released inside the layer via `Effect.acquireRelease`, and
 * `Layer.effect` discharges the resulting `Scope` so the pool closes when the
 * owning runtime scope ends. APIs follow effect-smol v4 (no `Layer.scoped`;
 * `Layer.effect` of a scoped effect).
 */
import { Context, Effect, Layer } from 'effect';
import { Pool, type QueryResultRow } from 'pg';
import { PG_URL } from '../config.ts';

export class Pg extends Context.Service<
  Pg,
  {
    readonly query: <T extends QueryResultRow = QueryResultRow>(
      text: string,
      params?: ReadonlyArray<unknown>
    ) => Effect.Effect<ReadonlyArray<T>>;
  }
>()('@spike/effect/Pg') {}

/** A `Pg` backed by a node-postgres pool whose lifetime is the layer's scope. */
export const PgLive: Layer.Layer<Pg> = Layer.effect(
  Pg,
  Effect.gen(function* () {
    const pool = yield* Effect.acquireRelease(
      Effect.sync(() => new Pool({ connectionString: PG_URL, max: 4 })),
      (acquired) => Effect.promise(() => acquired.end())
    );

    const query = <T extends QueryResultRow = QueryResultRow>(
      text: string,
      params: ReadonlyArray<unknown> = []
    ): Effect.Effect<ReadonlyArray<T>> =>
      Effect.promise(() => pool.query<T>(text, params as unknown[]).then((result) => result.rows));

    return { query } as const;
  })
);
