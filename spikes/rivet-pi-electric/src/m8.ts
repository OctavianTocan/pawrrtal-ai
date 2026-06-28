/**
 * M8 — Hatchet durable background workflow, surviving a worker restart.
 *
 * Proves the last 003 substrate piece: durable system work runs on Hatchet
 * (Postgres-backed queue), survives the worker dying, and projects into the app
 * Postgres through the SAME single-writer seam the actor uses.
 *
 * Phases (one process; Hatchet via infra/hatchet-compose.yml, app PG via
 * infra/docker-compose.yml):
 *   baseline — start the worker, run task A end-to-end → row A in PG.
 *   down     — SIGKILL the worker, then enqueue task B while nothing serves it;
 *              B must NOT be projected yet (it sits in Hatchet's PG queue).
 *   restart  — restart the worker → it picks B off the queue → row B in PG.
 *
 * Run:
 *   bun run m8
 */
import { type ChildProcess, spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { ensureReady } from './api.ts';
import { closePool, query } from './db.ts';
import { defineProjectSummary, makeHatchet, type ProjectSummaryInput } from './hatchet/workflow.ts';

const TOKEN_FILE = `${process.cwd()}/infra/hatchet-creds/api-token`;
const B_TIMEOUT_MS = 90000;

function out(line: string): void {
  process.stdout.write(`${line}\n`);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function spawnWorker(token: string): ChildProcess {
  return spawn('bun', ['run', 'src/hatchet/worker.ts'], {
    env: { ...process.env, HATCHET_CLIENT_TOKEN: token, HATCHET_CLIENT_TLS_STRATEGY: 'none' },
    stdio: 'inherit',
  });
}

/** True once the projection row for `id` exists in the app Postgres. */
async function rowExists(id: string): Promise<boolean> {
  const rows = await query('SELECT id FROM conversations WHERE id = $1', [id]);
  return rows.length > 0;
}

async function waitRowExists(id: string, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await rowExists(id)) {
      return true;
    }
    await delay(1000);
  }
  return false;
}

async function main(): Promise<void> {
  await ensureReady();

  const token = readFileSync(TOKEN_FILE, 'utf8').trim();
  process.env.HATCHET_CLIENT_TOKEN = token;

  const hatchet = makeHatchet();
  const task = defineProjectSummary(hatchet);

  const stamp = Date.now();
  const owner = `m8-${stamp}@example.com`;
  const idA = `m8a-${stamp}`;
  const idB = `m8b-${stamp}`;
  const inputA: ProjectSummaryInput = { id: idA, owner, title: 'A', lastMessage: 'task A', turnCount: 1 };
  const inputB: ProjectSummaryInput = {
    id: idB,
    owner,
    title: 'B',
    lastMessage: 'task B enqueued while worker down',
    turnCount: 1,
  };

  // --- baseline: worker up, run task A end-to-end (also registers the workflow) ---
  let worker = spawnWorker(token);
  await delay(6000);
  await task.run(inputA);
  const aProjected = await rowExists(idA);
  out(`[m8] baseline: task A ran; row A in PG=${aProjected}`);

  // --- down: kill the worker, enqueue B while nothing serves it ---
  worker.kill('SIGKILL');
  await delay(2000);
  const ref = await task.runNoWait(inputB);
  const runId = await ref.getWorkflowRunId();
  await delay(3000);
  const bBeforeRestart = await rowExists(idB);
  out(`[m8] down: enqueued B (runId=${runId}); B projected before restart=${bBeforeRestart} (expect false)`);

  // --- restart: bring the worker back; B must be picked off the durable queue ---
  worker = spawnWorker(token);
  const bAfterRestart = await waitRowExists(idB, B_TIMEOUT_MS);
  out(`[m8] restart: B projected after restart=${bAfterRestart} (expect true)`);

  worker.kill('SIGKILL');
  await delay(500);
  await closePool();

  const pass = aProjected && !bBeforeRestart && bAfterRestart;
  out(
    pass
      ? '\nM8 PASS — Hatchet durably queued the task across a worker restart and projected it through the API seam'
      : '\nM8 FAIL'
  );
  process.exit(pass ? 0 : 1);
}

main().catch((error) => {
  process.stderr.write(`M8 crashed: ${String(error)}\n`);
  process.exit(1);
});
