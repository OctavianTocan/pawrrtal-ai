/**
 * The API seam — the single writer of Postgres.
 *
 * In the real system this is `apps/api` reached over RPC; in the spike it is an
 * in-process function. Either way it is the ONLY path that writes the
 * `conversations` record. The Rivet actor calls `upsertConversationSummary`; it
 * never opens its own PG connection. That is the "single writer per store"
 * invariant from the 003 substrate ADR, made structural.
 */
import { ensureSchema, query } from './db.ts';

export interface ConversationSummary {
  readonly id: string;
  readonly owner: string;
  readonly title: string;
  readonly lastMessage: string;
  readonly turnCount: number;
}

/** Make sure the store is ready (delegates to the storage layer). */
export async function ensureReady(): Promise<void> {
  await ensureSchema();
}

/**
 * Upsert a conversation's summary row. Insert on first write, update its
 * `last_message` / `turn_count` / `updated_at` thereafter.
 */
export async function upsertConversationSummary(summary: ConversationSummary): Promise<void> {
  await query(
    `
    INSERT INTO conversations (id, owner, title, last_message, turn_count, updated_at)
    VALUES ($1, $2, $3, $4, $5, now())
    ON CONFLICT (id) DO UPDATE SET
      last_message = EXCLUDED.last_message,
      turn_count   = EXCLUDED.turn_count,
      updated_at   = now();
    `,
    [summary.id, summary.owner, summary.title, summary.lastMessage, summary.turnCount]
  );
}
