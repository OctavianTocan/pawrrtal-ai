/**
 * The single-writer API seam wrapped as an Effect v4 service (M7).
 *
 * Mirrors `api.ts`'s `upsertConversationSummary`, but as a `Conversations`
 * service that depends on {@link Pg}. `ConversationsLive` provides its own `Pg`,
 * so consumers get a self-contained layer — the same composition shape as
 * backend-ts `ProjectsRepoLive` (a `Layer.effect` body wired to its DB layer).
 */
import { Context, Effect, Layer } from 'effect';
import type { ConversationSummary } from '../api.ts';
import { Pg, PgLive } from './Pg.ts';

const UPSERT_SQL = `
  INSERT INTO conversations (id, owner, title, last_message, turn_count, updated_at)
  VALUES ($1, $2, $3, $4, $5, now())
  ON CONFLICT (id) DO UPDATE SET
    last_message = EXCLUDED.last_message,
    turn_count   = EXCLUDED.turn_count,
    updated_at   = now();
`;

export class Conversations extends Context.Service<
  Conversations,
  {
    readonly upsertSummary: (summary: ConversationSummary) => Effect.Effect<void>;
  }
>()('@spike/effect/Conversations') {}

/** `Conversations` requiring a `Pg`; wire with {@link ConversationsLive}. */
export const ConversationsBody: Layer.Layer<Conversations, never, Pg> = Layer.effect(
  Conversations,
  Effect.gen(function* () {
    const pg = yield* Pg;

    const upsertSummary = (summary: ConversationSummary): Effect.Effect<void> =>
      pg
        .query(UPSERT_SQL, [summary.id, summary.owner, summary.title, summary.lastMessage, summary.turnCount])
        .pipe(Effect.asVoid);

    return { upsertSummary } as const;
  })
);

/** Self-contained `Conversations` backed by its own PG pool. */
export const ConversationsLive: Layer.Layer<Conversations> = ConversationsBody.pipe(Layer.provide(PgLive));
