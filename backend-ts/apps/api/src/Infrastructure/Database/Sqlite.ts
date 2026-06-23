import { SqliteClient } from '@effect/sql-sqlite-bun';
import { Context, Effect, Layer } from 'effect';
import { DatabaseConfig } from './Config';

const DatabaseBase = SqliteClient.layerConfig(DatabaseConfig);

/** File-backed SQLite with `projects` schema applied on layer startup. */
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
