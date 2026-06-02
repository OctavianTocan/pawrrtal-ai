// Use @effect/sql-sqlite-node to connect to the SQLite database.
// Follow backend/vendor/effect-smol/packages/sql/sqlite-node/src/SqliteClient.ts:
// SqliteClient.layer or layerConfig for the implementation.

import { SqliteClient } from '@effect/sql-sqlite-node';
import { DatabaseConfig } from './Config';

/** The SQLite database layer. */
export const DatabaseLive = SqliteClient.layerConfig(DatabaseConfig);
