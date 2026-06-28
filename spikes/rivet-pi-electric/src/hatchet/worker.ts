/**
 * Standalone Hatchet worker (M8).
 *
 * Run as a child process so the M8 runner can SIGKILL it mid-flight and prove a
 * task enqueued while it was down still runs after it restarts. It registers the
 * one projection task and blocks in `worker.start()`.
 */
import { defineProjectSummary, makeHatchet } from './workflow.ts';

async function main(): Promise<void> {
  const hatchet = makeHatchet();
  const task = defineProjectSummary(hatchet);
  const worker = await hatchet.worker('spike-m8-worker', { workflows: [task] });
  process.stdout.write('[worker] starting\n');
  await worker.start();
}

main().catch((error) => {
  process.stderr.write(`[worker] crashed: ${String(error)}\n`);
  process.exit(1);
});
