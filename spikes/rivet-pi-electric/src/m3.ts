/**
 * M3 — Postgres single-writer projection + Electric read-path sync.
 *
 * Builds on M1/M2 (Pi-in-actor streaming + restart durability) and validates
 * the half the earlier gate skipped:
 *
 *   - the actor reaches Postgres ONLY through the API seam (single writer), and
 *   - a second client sees that row live via Electric (the read path that
 *     files-first never had).
 *
 * Phases:
 *   m3a    — raw sync: API writes a row → Electric pushes insert+update to a client.
 *   m3b    — actor projection: a Pi turn streams to client A (actor WS) AND the
 *            summary row appears in client B (Electric), single-writer.
 *   seed   — durability: one projected turn, then shut the runtime down.
 *   verify — after a cold restart (engine killed; PG+Electric kept running):
 *            the PG row replays via Electric, the actor replays its transcript
 *            from RocksDB, and a follow-up turn re-projects (turn_count 1 -> 2).
 *
 * Run (PG+Electric must be up via infra/docker-compose.yml):
 *   RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3a
 *   RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3b
 *   rm -rf .rivethome && mkdir -p .rivethome
 *   RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3c:seed
 *   pkill -f 'rivet-engine start'; sleep 5
 *   RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3c:verify
 */
import { ensureReady, upsertConversationSummary } from './api.ts';
import { closePool } from './db.ts';
import { bootConversation } from './harness.ts';
import { type ConversationRow, openConversationShape } from './shape-client.ts';

const WAIT_MS = 20000;
const DURABLE_KEY = ['conv-m3-durable'];
const DURABLE_ID = 'conv-m3-durable';
const DURABLE_OWNER = 'carol';

function out(line: string): void {
  process.stdout.write(`${line}\n`);
}

/** Electric parses ints, but coerce defensively for assertions. */
function turnCountOf(row: ConversationRow | undefined): number {
  return row ? Number(row.turn_count) : Number.NaN;
}

/** M3a — raw single-writer write → Electric read-path sync. */
async function m3a(): Promise<void> {
  await ensureReady();
  const id = `m3a-${Date.now()}`;
  const shape = openConversationShape();

  await upsertConversationSummary({
    id,
    owner: 'alice',
    title: 'Raw sync test',
    lastMessage: 'first write',
    turnCount: 1,
  });
  await shape.waitFor((rows) => turnCountOf(rows.get(id)) === 1, WAIT_MS);
  out(`[m3a] client B saw INSERT id=${id} turn_count=1`);

  await upsertConversationSummary({
    id,
    owner: 'alice',
    title: 'Raw sync test',
    lastMessage: 'second write',
    turnCount: 2,
  });
  await shape.waitFor(
    (rows) => turnCountOf(rows.get(id)) === 2 && rows.get(id)?.last_message === 'second write',
    WAIT_MS
  );
  out(`[m3a] client B saw UPDATE id=${id} turn_count=2`);

  shape.close();
  await closePool();
  out('\nM3a PASS — API write reached a second client live via Electric');
  process.exit(0);
}

/** M3b — actor projects through the API; client A streams, client B syncs. */
async function m3b(): Promise<void> {
  await ensureReady();
  const id = `m3b-${Date.now()}`;
  const owner = 'bob';
  const shape = openConversationShape();
  const { conn, cleanup } = await bootConversation([`spike-${id}`]);
  await conn.setIdentity({ id, owner });

  let streamed = '';
  let deltaCount = 0;
  conn.on('delta', (payload: { text: string }) => {
    streamed += payload.text;
    deltaCount += 1;
  });

  const result = await conn.sendMessage('What are you and where do you run?');
  await shape.waitFor((rows) => turnCountOf(rows.get(id)) === 1, WAIT_MS);
  const row = shape.rows.get(id);

  out(`[m3b] client A streamed ${deltaCount} deltas (${streamed.length} chars)`);
  out(`[m3b] client B row: id=${row?.id} owner=${row?.owner} turn_count=${row?.turn_count}`);
  out(`[m3b] title="${row?.title}"`);

  const ok = deltaCount > 0 && result.assistantText === streamed && turnCountOf(row) === 1 && row?.owner === owner;

  shape.close();
  await cleanup();
  await closePool();
  out(ok ? '\nM3b PASS — token live in A AND summary row live in B' : '\nM3b FAIL');
  process.exit(ok ? 0 : 1);
}

/** M3c seed — one projected turn, then shut the runtime down. */
async function seed(): Promise<void> {
  await ensureReady();
  const { conn, cleanup } = await bootConversation(DURABLE_KEY);
  await conn.setIdentity({ id: DURABLE_ID, owner: DURABLE_OWNER });
  const result = await conn.sendMessage('First message, before the restart.');
  out(`[seed] turnCount=${result.turnCount} transcriptLength=${result.transcriptLength}`);
  await cleanup();
  await closePool();
  out('[seed] runtime shut down; PG row + actor state should be on disk');
  process.exit(0);
}

/** M3c verify — PG row replays via Electric, actor replays, follow-up re-projects. */
async function verify(): Promise<void> {
  await ensureReady();

  const shape = openConversationShape();
  await shape.waitFor((rows) => rows.has(DURABLE_ID), WAIT_MS);
  const seeded = shape.rows.get(DURABLE_ID);
  const replayRowOk = turnCountOf(seeded) === 1;
  out(`[verify] Electric replayed PG row turn_count=${seeded?.turn_count} (persisted across restart)`);

  const { conn, cleanup } = await bootConversation(DURABLE_KEY);
  const transcript = await conn.getTranscript();
  const replayActorOk = transcript.turnCount === 1 && transcript.messageCount === 2;
  out(`[verify] actor replayed turnCount=${transcript.turnCount} messageCount=${transcript.messageCount}`);

  await conn.setIdentity({ id: DURABLE_ID, owner: DURABLE_OWNER });
  const result = await conn.sendMessage('Second message, after the restart.');
  const continueActorOk = result.turnCount === 2 && result.transcriptLength === 4;
  out(`[verify] continued turnCount=${result.turnCount} transcriptLength=${result.transcriptLength}`);

  await shape.waitFor((rows) => turnCountOf(rows.get(DURABLE_ID)) === 2, WAIT_MS);
  out('[verify] Electric synced post-restart UPDATE turn_count=2');

  shape.close();
  await cleanup();
  await closePool();

  const ok = replayRowOk && replayActorOk && continueActorOk;
  out(
    ok
      ? '\nM3c PASS — PG row + actor state survived the cold restart and continued in sync'
      : `\nM3c FAIL — replayRowOk=${replayRowOk} replayActorOk=${replayActorOk} continueActorOk=${continueActorOk}`
  );
  process.exit(ok ? 0 : 1);
}

const phase = process.argv[2];
const phases: Record<string, () => Promise<void>> = { m3a, m3b, seed, verify };
const run = phase ? phases[phase] : undefined;
if (!run) {
  process.stderr.write('usage: bun run src/m3.ts <m3a|m3b|seed|verify>\n');
  process.exit(2);
}
run().catch((error) => {
  process.stderr.write(`M3 ${phase} crashed: ${String(error)}\n`);
  process.exit(1);
});
