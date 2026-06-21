/**
 * Build a fresh, schema-loaded `:memory:` SQLite layer per test suite.
 *
 * Why `:memory:`:
 * - No file system side effects; the test process can't leak schema
 *   state to other tests or to the developer's `pawrrtal.db`.
 * - Avoids the dual-process lock concern from the pilot plan §4.3 —
 *   that concern is file-backed SQLite opened by two processes;
 *   `:memory:` is per-process.
 *
 * Why `Layer.effectContext` (not `Layer.unwrap` of a `Layer.make`
 * Effect): `Layer.unwrap` calls `Layer.flatMap` internally;
 * `effectContext` runs the effect in the layer's scope and returns the
 * resulting `Context` as the provided services. The schema runs as
 * part of layer acquisition; on scope close the client is released.
 *
 * Schema mirrors `backend/app/models.py` → `projects` table.
 */
import { SqliteClient } from '@effect/sql-sqlite-bun';
import { Context, Effect, Layer, Scope } from 'effect';
import { Reactivity } from 'effect/unstable/reactivity';
import { SqlClient } from 'effect/unstable/sql';

export const makeInMemoryDatabase = (): Layer.Layer<
	SqliteClient.SqliteClient | SqlClient.SqlClient
> =>
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
			return Context.make(SqliteClient.SqliteClient, client).pipe(
				Context.add(SqlClient.SqlClient, client)
			);
		})
	).pipe(Layer.provide(Reactivity.layer));
