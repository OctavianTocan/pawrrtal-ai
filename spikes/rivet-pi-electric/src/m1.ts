/**
 * M1 — Pi-in-actor streaming.
 *
 * Boots the Rivet registry in-process (rivetkit's `setupTest` harness, driven
 * from a plain script via a stub test context), connects a client to the
 * conversation actor, sends a message, and prints every `text_delta` the actor
 * broadcasts while the unforked Pi loop runs. Success = tokens appear live and
 * the returned transcript is non-empty.
 *
 * Run: `bun run src/m1.ts`
 */
import { bootConversation } from './harness.ts';

/** Write a line to stdout (this is a CLI runner; stdout is the product). */
function out(line: string): void {
  process.stdout.write(`${line}\n`);
}

async function main(): Promise<void> {
  const { conn, cleanup } = await bootConversation(['spike-conversation']);

  let streamed = '';
  let deltaCount = 0;
  conn.on('delta', (payload: { text: string }) => {
    streamed += payload.text;
    deltaCount += 1;
    process.stdout.write(payload.text);
  });
  conn.on('turn_done', (payload: { stopReason: string }) => {
    process.stdout.write(`\n[turn_done stopReason=${payload.stopReason}]\n`);
  });

  out('--- sending message, streaming live tokens below ---\n');
  const result = await conn.sendMessage('Tell me what you are and where you run.');

  // Give any trailing broadcasts a moment to drain to this connection.
  await new Promise((resolve) => setTimeout(resolve, 100));

  const transcript = await conn.getTranscript();

  out('\n--- result ---');
  out(JSON.stringify(result, null, 2));
  out(`deltas received: ${deltaCount}`);
  out(`streamed length: ${streamed.length}`);
  out(`transcript messageCount: ${transcript.messageCount}`);

  const ok = deltaCount > 0 && streamed.length > 0 && result.assistantText === streamed && transcript.messageCount >= 2;
  out(ok ? '\nM1 PASS' : '\nM1 FAIL');

  await cleanup();
  process.exit(ok ? 0 : 1);
}

main().catch((error) => {
  process.stderr.write(`M1 crashed: ${String(error)}\n`);
  process.exit(1);
});
