/**
 * The Postgres connection — the ONLY module in the spike that talks to PG.
 *
 * Keeping every `pg` call behind this module (and exposing writes solely
 * through `api.ts`) is what makes the "single writer per store" invariant
 * visible: the Rivet actor never imports `db.ts`, only `api.ts`.
 *
 * The pool is created lazily on first use so that importing this module (which
 * the actor's projection path pulls in transitively) does NOT open a PG
 * connection. M1/M2, which never project, therefore never touch Postgres.
 */
import { Pool } from 'pg';
import { PG_URL } from './config.ts';

let pool: Pool | undefined;

/** Lazily-created shared pool. */
function getPool(): Pool {
  if (!pool) {
    pool = new Pool({ connectionString: PG_URL, max: 4 });
  }
  return pool;
}

/** Create the one table the spike projects into. Idempotent. */
export async function ensureSchema(): Promise<void> {
  await getPool().query(`
    CREATE TABLE IF NOT EXISTS conversations (
      id           TEXT PRIMARY KEY,
      owner        TEXT NOT NULL,
      title        TEXT NOT NULL,
      last_message TEXT NOT NULL,
      turn_count   INTEGER NOT NULL,
      updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );
  `);
}

/** Run a parameterized query. Internal to the storage layer. */
export async function query<R extends Record<string, unknown>>(
  text: string,
  params: ReadonlyArray<unknown>
): Promise<R[]> {
  const result = await getPool().query(text, params as unknown[]);
  return result.rows as R[];
}

/** Close the pool (spike cleanup). */
export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = undefined;
  }
}
