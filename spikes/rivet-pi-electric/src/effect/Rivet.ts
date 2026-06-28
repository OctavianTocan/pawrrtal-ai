/**
 * The Rivet actor client wrapped as an Effect v4 service (M7).
 *
 * The raw client is rivetkit's `createClient` against the standalone server.
 * `sendMessage` / `transcript` open a connection, run the action, and always
 * dispose it. The layer is endpoint-parameterized (`makeRivetLive`) so tests
 * point it at whatever server they booted.
 */
import { Context, Effect, Layer } from 'effect';
import { createClient } from 'rivetkit/client';
import type { Registry } from '../registry.ts';

export interface RivetTurn {
  readonly turnCount: number;
  readonly transcriptLength: number;
}

export interface RivetTranscript {
  readonly turnCount: number;
  readonly messageCount: number;
}

export class Rivet extends Context.Service<
  Rivet,
  {
    readonly sendMessage: (key: ReadonlyArray<string>, text: string) => Effect.Effect<RivetTurn>;
    readonly transcript: (key: ReadonlyArray<string>) => Effect.Effect<RivetTranscript>;
  }
>()('@spike/effect/Rivet') {}

/** A `Rivet` that connects to the actor server at `endpoint`. */
export const makeRivetLive = (endpoint: string): Layer.Layer<Rivet> =>
  Layer.succeed(Rivet, {
    sendMessage: (key, text) =>
      Effect.tryPromise(async () => {
        const conn = createClient<Registry>(endpoint)
          .conversation.getOrCreate([...key])
          .connect();
        try {
          const result = await conn.sendMessage(text);
          return { turnCount: result.turnCount, transcriptLength: result.transcriptLength };
        } finally {
          await conn.dispose();
        }
      }).pipe(Effect.orDie),

    transcript: (key) =>
      Effect.tryPromise(async () => {
        const conn = createClient<Registry>(endpoint)
          .conversation.getOrCreate([...key])
          .connect();
        try {
          const result = await conn.getTranscript();
          return { turnCount: result.turnCount, messageCount: result.messageCount };
        } finally {
          await conn.dispose();
        }
      }).pipe(Effect.orDie),
  });
