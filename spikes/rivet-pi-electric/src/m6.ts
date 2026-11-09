/**
 * M6 — engine lifecycle off the test harness, durable across a cold restart.
 *
 * M1–M5 booted via `rivetkit/test`'s `setupTest`. M6 runs the actor under the
 * production standalone shape (`src/server.ts`: `startEngine` + pinned
 * `engineVersion`/`envoy.version` + `registry.start()`), connects with an
 * external `createClient`, and proves state survives a REAL cold restart that
 * this runner performs itself.
 *
 * No Postgres/Electric — this isolates the engine/runner durability (the PG
 * projection path was already proven in M3c). The actor's RocksDB state lives
 * under `.rivethome-m6`; the same dir is reused across the restart so state
 * replays, and the engine version is pinned so the runner re-registers.
 *
 * Phases (one process):
 *   seed     — boot server, send turn 1 (transcript = 2 messages).
 *   restart  — kill the server AND the engine, wait for :6420 to free.
 *   replay   — boot server again, read transcript: turn 1 still there.
 *   continue — send turn 2 on the replayed state (transcript = 4 messages).
 *
 * Run (no infra needed):
 *   bun run m6
 */
import { mkdirSync, rmSync } from 'node:fs';
import { createClient } from 'rivetkit/client';
import type { Registry } from './registry.ts';
import { type ServerOptions, spawnServer, stopServer, waitForReady, waitPortFree } from './server-control.ts';

const ENGINE_PORT = 6420;
const ENDPOINT = `http://127.0.0.1:${ENGINE_PORT}`;
const HOME_DIR = `${process.cwd()}/.rivethome-m6`;
const SERVER: ServerOptions = { enginePort: ENGINE_PORT, engineVersion: '1', homeDir: HOME_DIR };
const DURABLE_KEY = ['conv-m6-durable'];
// The actor persists its state to the engine over the wire; the turn resolving
// only means the in-memory state changed, not that the engine flushed it to
// RocksDB. Settle before the cold kill so we test DURABILITY of committed state,
// not a torn write (mirrors M2/M3c's pre-kill pause).
const SETTLE_MS = 3000;

function out(line: string): void {
  process.stdout.write(`${line}\n`);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main(): Promise<void> {
  // Deterministic reruns: start each run from empty engine state.
  rmSync(HOME_DIR, { recursive: true, force: true });
  mkdirSync(HOME_DIR, { recursive: true });

  // --- seed ---
  let server = spawnServer(SERVER);
  await waitForReady(ENDPOINT);
  const conn1 = createClient<Registry>(ENDPOINT).conversation.getOrCreate(DURABLE_KEY).connect();
  const seed = await conn1.sendMessage('first message before restart');
  out(`[m6] seed: turnCount=${seed.turnCount} transcriptLength=${seed.transcriptLength}`);
  await conn1.dispose();
  await delay(SETTLE_MS);

  // --- cold restart: kill the server AND the engine ---
  await stopServer(server);
  await waitPortFree(ENGINE_PORT);
  out('[m6] cold restart: server + engine down, :6420 free');

  // --- replay + continue ---
  server = spawnServer(SERVER);
  await waitForReady(ENDPOINT);
  const conn2 = createClient<Registry>(ENDPOINT).conversation.getOrCreate(DURABLE_KEY).connect();
  const replay = await conn2.getTranscript();
  out(`[m6] replay: turnCount=${replay.turnCount} messageCount=${replay.messageCount}`);
  const post = await conn2.sendMessage('second message after restart');
  out(`[m6] continue: turnCount=${post.turnCount} transcriptLength=${post.transcriptLength}`);
  await conn2.dispose();
  await stopServer(server);

  const pass =
    seed.turnCount === 1 &&
    seed.transcriptLength === 2 &&
    replay.turnCount === 1 &&
    replay.messageCount === 2 &&
    post.turnCount === 2 &&
    post.transcriptLength === 4;

  out(
    pass
      ? '\nM6 PASS — actor state durable across a real cold restart under the production engine config (startEngine + pinned engineVersion/envoy.version), off the setupTest harness'
      : '\nM6 FAIL'
  );
  process.exit(pass ? 0 : 1);
}

main().catch((error) => {
  process.stderr.write(`M6 crashed: ${String(error)}\n`);
  process.exit(1);
});
