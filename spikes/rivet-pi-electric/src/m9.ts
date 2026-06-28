/**
 * M9 — actor scheduler/alarm durability across a cold restart.
 *
 * The ADR names BOTH "alarm" and "state" durability as the first RC risks to
 * validate; M2/M3c/M6 proved state durability, but the actor's OWN scheduler
 * (`c.schedule.after(...)` → a named action) — the session-scoped timer the ADR
 * puts on the actor rather than Hatchet — was never exercised. M9 closes that:
 * a wake registered before a real cold restart must still fire (and mutate
 * state) after the actor rehydrates on a fresh engine, with no client invoking
 * the callback.
 *
 * No Postgres/Electric — this isolates the scheduler (same standalone engine
 * shape as M6). State lives under `.rivethome-m9`, reused across the restart.
 *
 * Phases (one process):
 *   schedule — boot server, register a wake WAKE_DELAY_MS out, settle so it
 *              persists, confirm it has NOT fired yet.
 *   restart  — kill the server AND the engine while the wake is still pending,
 *              wait for :6420 to free, boot again.
 *   fire     — after reboot the scheduler fires the wake on its own (either it
 *              was still pending, or its time elapsed during downtime and it
 *              catches up on rehydration) → wakeCount=1, label matches. It was
 *              0 before the restart, so the increment is the durable schedule.
 *
 * Run (no infra needed; ensure :6420 is free first):
 *   bun run m9
 */
import { mkdirSync, rmSync } from 'node:fs';
import { createClient } from 'rivetkit/client';
import type { Registry } from './registry.ts';
import { type ServerOptions, spawnServer, stopServer, waitForReady, waitPortFree } from './server-control.ts';

const ENGINE_PORT = 6420;
const ENDPOINT = `http://127.0.0.1:${ENGINE_PORT}`;
const HOME_DIR = `${process.cwd()}/.rivethome-m9`;
const SERVER: ServerOptions = { enginePort: ENGINE_PORT, engineVersion: '1', homeDir: HOME_DIR };
const DURABLE_KEY = ['conv-m9-wake'];
// Long enough that the wake cannot fire before the cold kill (kill lands ~5s
// in), but the engine reboot (boot + runner registration) can itself take
// ~20-30s — so the wake may be pending at reboot OR already overdue and caught
// up on rehydration. Both prove durability. Persisting the schedule is async
// w.r.t. the call returning (see FINDINGS #12), so settle before the cold kill.
const WAKE_DELAY_MS = 20000;
const SETTLE_MS = 3000;
const FIRE_TIMEOUT_MS = 45000;

function out(line: string): void {
  process.stdout.write(`${line}\n`);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function client() {
  return createClient<Registry>(ENDPOINT).conversation.getOrCreate(DURABLE_KEY).connect();
}

async function readWakes(): Promise<{ wakeCount: number; lastWakeLabel: string | null }> {
  const conn = client();
  try {
    return await conn.getWakes();
  } finally {
    await conn.dispose();
  }
}

async function main(): Promise<void> {
  rmSync(HOME_DIR, { recursive: true, force: true });
  mkdirSync(HOME_DIR, { recursive: true });

  const label = `wake-${Date.now()}`;

  // --- schedule ---
  let server = spawnServer(SERVER);
  await waitForReady(ENDPOINT);
  const conn1 = client();
  await conn1.scheduleWake({ delayMs: WAKE_DELAY_MS, label });
  await conn1.dispose();
  await delay(SETTLE_MS);
  const beforeRestart = await readWakes();
  out(`[m9] schedule: wake '${label}' set for +${WAKE_DELAY_MS}ms; wakeCount=${beforeRestart.wakeCount} (expect 0)`);

  // --- cold restart while the wake is still pending ---
  await stopServer(server);
  await waitPortFree(ENGINE_PORT);
  out('[m9] cold restart: server + engine down, :6420 free');
  server = spawnServer(SERVER);
  await waitForReady(ENDPOINT);

  // --- fire: the scheduler fires the pending/overdue wake after rehydration ---
  const atReboot = await readWakes();
  out(
    `[m9] reboot: wakeCount=${atReboot.wakeCount} (${atReboot.wakeCount === 0 ? 'still pending' : 'caught up on rehydration'})`
  );

  const deadline = Date.now() + FIRE_TIMEOUT_MS;
  let fired = atReboot;
  while (Date.now() < deadline && fired.wakeCount === 0) {
    await delay(1000);
    fired = await readWakes();
  }
  out(`[m9] fire: wakeCount=${fired.wakeCount} lastWakeLabel=${fired.lastWakeLabel} (expect 1 / '${label}')`);

  await stopServer(server);

  // The wake did NOT fire before the cold restart (0 at settle, long before its
  // fire time), and DID fire afterward with the right payload — whether still
  // pending at reboot or caught up on rehydration. fireWake is only ever invoked
  // by the scheduler, so the post-restart increment is the durable schedule.
  const pass = beforeRestart.wakeCount === 0 && fired.wakeCount === 1 && fired.lastWakeLabel === label;

  out(
    pass
      ? '\nM9 PASS — a per-session scheduled wake survived a real cold restart and fired (mutating state) after the actor rehydrated, with no client invoking it'
      : '\nM9 FAIL'
  );
  process.exit(pass ? 0 : 1);
}

main().catch((error) => {
  process.stderr.write(`M9 crashed: ${String(error)}\n`);
  process.exit(1);
});
