/**
 * M7 — the substrate clients wrapped as Effect v4 layers.
 *
 * M1–M6 used the raw clients directly (node-postgres `Pool`,
 * `@electric-sql/client` ShapeStream, rivetkit `createClient`). M7 proves the
 * 003 wrapping pattern: each raw client becomes an Effect `Service` with a
 * `Layer` (PG as a scoped pool via `Layer.effect` + `acquireRelease`; Electric
 * and Rivet as `Layer.succeed`), composed with `Layer.mergeAll` and run once via
 * `Effect.runPromise`. The idiom follows effect-smol v4 (`Context.Service` /
 * `Layer` / `Effect.gen`), matching backend-ts `apps/api`.
 *
 * Runtime proof (reuses M3/M5 PG+Electric infra + a brief standalone server):
 *   pg+electric — write a summary through the wrapped Conversations seam (over
 *                 the scoped PG pool), then read it back through the wrapped
 *                 Electric shape.
 *   rivet       — run a turn and read the transcript through the wrapped Rivet
 *                 client against the standalone actor server.
 *
 * Run (PG + Electric up via infra/docker-compose.yml):
 *   bun run m7
 */
import { mkdirSync, rmSync } from 'node:fs';
import { Effect, Layer } from 'effect';
import { ensureReady } from './api.ts';
import { Conversations, ConversationsLive, Electric, ElectricLive, makeRivetLive, Rivet } from './effect/index.ts';
import { type ServerOptions, spawnServer, stopServer, waitForReady } from './server-control.ts';

const ENGINE_PORT = 6420;
const ENDPOINT = `http://127.0.0.1:${ENGINE_PORT}`;
const HOME_DIR = `${process.cwd()}/.rivethome-m7`;
const SERVER: ServerOptions = { enginePort: ENGINE_PORT, engineVersion: '1', homeDir: HOME_DIR };

function out(line: string): void {
  process.stdout.write(`${line}\n`);
}

async function main(): Promise<void> {
  await ensureReady();
  rmSync(HOME_DIR, { recursive: true, force: true });
  mkdirSync(HOME_DIR, { recursive: true });

  const server = spawnServer(SERVER);
  await waitForReady(ENDPOINT);

  const stamp = Date.now();
  const id = `m7-${stamp}`;
  const owner = `m7-${stamp}@example.com`;

  const layer = Layer.mergeAll(ConversationsLive, ElectricLive, makeRivetLive(ENDPOINT));

  const program = Effect.gen(function* () {
    const conversations = yield* Conversations;
    const electric = yield* Electric;
    const rivet = yield* Rivet;

    // pg + electric: write through the wrapped seam, read through the wrapped shape.
    yield* conversations.upsertSummary({
      id,
      owner,
      title: 'M7 wrapped',
      lastMessage: 'written via Effect',
      turnCount: 1,
    });
    const row = yield* electric.awaitRow(id, { timeoutMs: 20000 });

    // rivet: run a turn and read the transcript through the wrapped client.
    const turn = yield* rivet.sendMessage(['m7-conv'], 'hello through the wrapped client');
    const transcript = yield* rivet.transcript(['m7-conv']);

    return { row, turn, transcript };
  });

  const { row, turn, transcript } = await Effect.runPromise(program.pipe(Effect.provide(layer)));

  await stopServer(server);

  const pgElectricOk = row.id === id && row.owner === owner && row.turn_count === 1;
  const rivetOk = turn.turnCount === 1 && transcript.turnCount === 1 && transcript.messageCount === 2;
  out(`[m7] pg+electric: row.owner=${row.owner} turn_count=${row.turn_count} ok=${pgElectricOk}`);
  out(
    `[m7] rivet: turn=${turn.turnCount} transcript.turnCount=${transcript.turnCount} messageCount=${transcript.messageCount} ok=${rivetOk}`
  );

  const pass = pgElectricOk && rivetOk;
  out(
    pass
      ? '\nM7 PASS — PG, Electric, and Rivet wrapped as Effect v4 layers and exercised through one composed runtime'
      : '\nM7 FAIL'
  );
  process.exit(pass ? 0 : 1);
}

main().catch((error) => {
  process.stderr.write(`M7 crashed: ${String(error)}\n`);
  process.exit(1);
});
