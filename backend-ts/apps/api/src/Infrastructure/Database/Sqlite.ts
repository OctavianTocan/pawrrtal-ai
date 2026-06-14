// Use @effect/sql-sqlite-bun to connect to the SQLite database, then run
// the production schema as part of layer acquisition. Schema mirrors
// `backend/app/models.py` and `backend-ts/apps/api/test/unit/_helpers/
// InMemoryDatabase.ts` (the test helper applies the same DDL on a fresh
// `:memory:` connection per suite; production needs the same bootstrap
// because the file-backed `pawrrtal.db` is otherwise empty and the
// first `INSERT` would fail with `SQLiteError: no such table: projects`).
//
// Approach: `SqliteClient.layerConfig` to acquire the client from the
// resolved config, then `Layer.tap` to run the DDL on the same
// connection. The tap runs after the upstream layer is built, so the
// SqliteClient tag is already populated when the migration fires.

import { SqliteClient } from '@effect/sql-sqlite-bun';
import { Context, Effect, Layer } from 'effect';
import { DatabaseConfig } from './Config';

const DatabaseBase = SqliteClient.layerConfig(DatabaseConfig);

/** Production SQLite layer — opens the file, runs schema DDL, hands the client to Repo layers. */
export const DatabaseLive = DatabaseBase.pipe(
	Layer.tap((ctx) =>
		Effect.gen(function* () {
			const client = Context.get(ctx, SqliteClient.SqliteClient);
			yield* client`CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )`;
		})
	)
);
