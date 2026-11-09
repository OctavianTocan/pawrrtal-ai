/**
 * M4 — identity-scoped Electric gatekeeper.
 *
 * M3 proved the write path (actor → API → Postgres → Electric → client). M4
 * proves the read path is SAFE for a public, multi-tenant audience: a client
 * may only ever sync its own rows, and that scope is enforced by the server,
 * not trusted from the client.
 *
 * No Rivet engine here — this is purely the read path (rows written directly
 * through the single-writer API seam, then read back through the proxy).
 *
 * Phases (all in one process):
 *   scope   — alice and bob each own a row. A client authenticating as alice
 *             (via the proxy) sees ONLY alice's row, never bob's.
 *   sneak   — a client authenticating as alice but asking for `where owner=bob`
 *             STILL sees only alice's row (the proxy drops the client where and
 *             forces `owner = $1`).
 *   reject  — a request with no identity → 401; a request for a non-allowlisted
 *             table → 403.
 *
 * Run (PG + Electric must be up via infra/docker-compose.yml):
 *   bun run m4
 */
import { ensureReady, upsertConversationSummary } from './api.ts';
import { PROXY_PORT, PROXY_URL } from './config.ts';
import { closePool } from './db.ts';
import { startProxy } from './proxy.ts';
import { openConversationShape } from './shape-client.ts';

const WAIT_MS = 20000;
/** After a client's own row arrives, wait this long to prove the other owner's never does. */
const GRACE_MS = 4000;
const SHAPE_ENDPOINT = `${PROXY_URL}/v1/shape`;

function out(line: string): void {
  process.stdout.write(`${line}\n`);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main(): Promise<void> {
  await ensureReady();

  const stamp = Date.now();
  const alice = `alice-${stamp}@example.com`;
  const bob = `bob-${stamp}@example.com`;
  const aliceConv = `m4-alice-${stamp}`;
  const bobConv = `m4-bob-${stamp}`;

  // Seed one row per owner via the single-writer API seam.
  await upsertConversationSummary({
    id: aliceConv,
    owner: alice,
    title: 'Alice chat',
    lastMessage: 'hi from alice',
    turnCount: 1,
  });
  await upsertConversationSummary({
    id: bobConv,
    owner: bob,
    title: 'Bob chat',
    lastMessage: 'hi from bob',
    turnCount: 1,
  });

  const server = startProxy(PROXY_PORT);
  out(`[m4] gatekeeper proxy listening on ${PROXY_URL}`);

  let pass = true;

  // --- scope: alice sees only her own row ---
  const aliceShape = openConversationShape({
    url: SHAPE_ENDPOINT,
    headers: { 'x-spike-user': alice },
  });
  await aliceShape.waitFor((rows) => rows.has(aliceConv), WAIT_MS);
  await delay(GRACE_MS);
  const aliceSeesOwn = aliceShape.rows.has(aliceConv);
  const aliceSeesBob = aliceShape.rows.has(bobConv);
  const aliceOnlyOwnOwner = [...aliceShape.rows.values()].every((row) => row.owner === alice);
  out(
    `[m4] scope: alice ownRow=${aliceSeesOwn} bobRow=${aliceSeesBob} onlyOwnOwner=${aliceOnlyOwnOwner} rows=${aliceShape.rows.size}`
  );
  if (!aliceSeesOwn || aliceSeesBob || !aliceOnlyOwnOwner) {
    pass = false;
  }
  aliceShape.close();

  // --- sneak: alice asks for bob's rows; proxy ignores the client where ---
  const sneaky = openConversationShape({
    url: SHAPE_ENDPOINT,
    headers: { 'x-spike-user': alice },
    where: `owner = '${bob}'`,
  });
  await sneaky.waitFor((rows) => rows.has(aliceConv), WAIT_MS).catch(() => undefined);
  await delay(GRACE_MS);
  const sneakSeesBob = sneaky.rows.has(bobConv);
  out(`[m4] sneak: alice-asking-for-bob bobRow=${sneakSeesBob} (must be false)`);
  if (sneakSeesBob) {
    pass = false;
  }
  sneaky.close();

  // --- reject: missing identity → 401 ---
  const noIdentity = await fetch(`${SHAPE_ENDPOINT}?table=conversations&offset=-1`);
  await noIdentity.body?.cancel();
  out(`[m4] reject: no-identity status=${noIdentity.status} (expect 401)`);
  if (noIdentity.status !== 401) {
    pass = false;
  }

  // --- reject: non-allowlisted table → 403 ---
  const badTable = await fetch(`${SHAPE_ENDPOINT}?table=secrets&offset=-1`, {
    headers: { 'x-spike-user': alice },
  });
  await badTable.body?.cancel();
  out(`[m4] reject: bad-table status=${badTable.status} (expect 403)`);
  if (badTable.status !== 403) {
    pass = false;
  }

  server.close();
  await closePool();

  out(
    pass
      ? '\nM4 PASS — gatekeeper enforces owner scope + table allowlist server-side; clients cannot widen their view'
      : '\nM4 FAIL'
  );
  process.exit(pass ? 0 : 1);
}

main().catch((error) => {
  process.stderr.write(`M4 crashed: ${String(error)}\n`);
  process.exit(1);
});
