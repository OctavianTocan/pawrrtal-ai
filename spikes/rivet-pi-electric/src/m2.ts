/**
 * M2 — durability across a real restart.
 *
 * Two separate process invocations share one on-disk Rivet engine DB (via a
 * stable `$HOME/.rivetkit`):
 *
 *   1. `bun run src/m2.ts seed`   — send one turn to the "conv-durable" actor,
 *                                    then shut the runtime down.
 *   2. `bun run src/m2.ts verify` — boot a fresh process, read the transcript
 *                                    (must replay the seeded turn from disk),
 *                                    then send another turn and confirm the
 *                                    turn counter continued from the persisted
 *                                    value rather than resetting.
 *
 * Success = the seeded transcript survives the restart AND the follow-up turn
 * builds on it (turnCount 1 -> 2, messages 2 -> 4).
 */
import { bootConversation } from './harness.ts';

/** Write a line to stdout (this is a CLI runner; stdout is the product). */
function out(line: string): void {
  process.stdout.write(`${line}\n`);
}

const ACTOR_KEY = ['conv-durable'];

async function seed(): Promise<void> {
  const { conn, cleanup } = await bootConversation(ACTOR_KEY);
  const result = await conn.sendMessage('First message, before the restart.');
  out(`[seed] turnCount: ${result.turnCount}`);
  out(`[seed] transcriptLength: ${result.transcriptLength}`);
  await cleanup();
  out('[seed] runtime shut down; state should be on disk');
  process.exit(0);
}

async function verify(): Promise<void> {
  const { conn, cleanup } = await bootConversation(ACTOR_KEY);

  const replayed = await conn.getTranscript();
  out(`[verify] replayed turnCount: ${replayed.turnCount}`);
  out(`[verify] replayed messageCount: ${replayed.messageCount}`);

  const replayOk = replayed.turnCount === 1 && replayed.messageCount === 2;

  const result = await conn.sendMessage('Second message, after the restart.');
  out(`[verify] continued turnCount: ${result.turnCount}`);
  out(`[verify] continued transcriptLength: ${result.transcriptLength}`);

  const continueOk = result.turnCount === 2 && result.transcriptLength === 4;

  await cleanup();

  const ok = replayOk && continueOk;
  out(
    ok
      ? '\nM2 PASS — state replayed from disk and the next turn continued it'
      : `\nM2 FAIL — replayOk=${replayOk} continueOk=${continueOk}`
  );
  process.exit(ok ? 0 : 1);
}

const phase = process.argv[2];
const run = phase === 'seed' ? seed : phase === 'verify' ? verify : undefined;
if (!run) {
  process.stderr.write('usage: bun run src/m2.ts <seed|verify>\n');
  process.exit(2);
}
run().catch((error) => {
  process.stderr.write(`M2 ${phase} crashed: ${String(error)}\n`);
  process.exit(1);
});
