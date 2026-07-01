/** In-memory SQLite layer with `projects` schema for tests. */

import { SqliteClient } from '@effect/sql-sqlite-bun';
import { Context, Effect, Layer, Scope } from 'effect';
import { Reactivity } from 'effect/unstable/reactivity';
import { SqlClient } from 'effect/unstable/sql';

export const makeInMemoryDatabase = (): Layer.Layer<SqliteClient.SqliteClient | SqlClient.SqlClient> =>
  Layer.effectContext(
    Effect.gen(function* () {
      const client = yield* SqliteClient.make({ filename: ':memory:' });
      yield* client`CREATE TABLE projects (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )`;
      yield* Scope.addFinalizer(
        yield* Effect.scope,
        Effect.sync(() => client)
      );
      return Context.make(SqliteClient.SqliteClient, client).pipe(Context.add(SqlClient.SqlClient, client));
    })
    // Schema decode failures in setup are programmer errors, not test assertions.
  ).pipe(Layer.orDie, Layer.provide(Reactivity.layer));
