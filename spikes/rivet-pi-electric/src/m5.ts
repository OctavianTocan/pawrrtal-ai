/**
 * M5 — real session identity behind the gatekeeper.
 *
 * M4 proved the proxy scopes reads per owner, but it trusted an `x-spike-user`
 * header — i.e. the client asserted its own identity. That is unsafe for a
 * public audience. M5 closes the gap: identity is resolved through a trusted
 * authority (the {@link createSessionStore} stand-in for `/users/me`), and a
 * client-asserted value carries no weight.
 *
 * No new infra — reuses M4's Postgres + Electric.
 *
 * Phases (one process):
 *   session-scope     — a validated session for alice syncs only alice's rows.
 *   header-not-trusted — alice's session + `x-spike-user: bob` still yields only
 *                        alice's rows (the asserted header is ignored).
 *   reject             — forged session → 401, no credential → 401, revoked
 *                        session → 401.
 *
 * Run (PG + Electric must be up via infra/docker-compose.yml):
 *   bun run m5
 */
import { ensureReady, upsertConversationSummary } from './api.ts';
import { PROXY_PORT, PROXY_URL } from './config.ts';
import { closePool } from './db.ts';
import { sessionAuth, startProxy } from './proxy.ts';
import { createSessionStore } from './session-store.ts';
import { openConversationShape } from './shape-client.ts';

const WAIT_MS = 20000;
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
  const aliceConv = `m5-alice-${stamp}`;
  const bobConv = `m5-bob-${stamp}`;

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

  // The trusted authority mints sessions; the proxy resolves identity via it.
  const store = createSessionStore();
  const aliceSession = store.create(alice);
  const bobSession = store.create(bob);

  const server = startProxy(PROXY_PORT, sessionAuth(store));
  out(`[m5] gatekeeper (session identity) listening on ${PROXY_URL}`);

  let pass = true;

  // --- a validated session scopes to its owner ---
  const aliceShape = openConversationShape({
    url: SHAPE_ENDPOINT,
    headers: { Authorization: `Bearer ${aliceSession}` },
  });
  await aliceShape.waitFor((rows) => rows.has(aliceConv), WAIT_MS);
  await delay(GRACE_MS);
  const aliceOk =
    aliceShape.rows.has(aliceConv) &&
    !aliceShape.rows.has(bobConv) &&
    [...aliceShape.rows.values()].every((row) => row.owner === alice);
  out(
    `[m5] session-scope: alice ownRow=${aliceShape.rows.has(aliceConv)} bobRow=${aliceShape.rows.has(bobConv)} rows=${aliceShape.rows.size}`
  );
  if (!aliceOk) {
    pass = false;
  }
  aliceShape.close();

  // --- a client-asserted header is NOT trusted ---
  const spoof = openConversationShape({
    url: SHAPE_ENDPOINT,
    headers: { Authorization: `Bearer ${aliceSession}`, 'x-spike-user': bob },
  });
  await spoof.waitFor((rows) => rows.has(aliceConv), WAIT_MS).catch(() => undefined);
  await delay(GRACE_MS);
  const spoofSawBob = spoof.rows.has(bobConv);
  out(`[m5] header-not-trusted: alice-session + x-spike-user=bob -> bobRow=${spoofSawBob} (must be false)`);
  if (spoofSawBob) {
    pass = false;
  }
  spoof.close();

  // --- forged session -> 401 ---
  const forged = await fetch(`${SHAPE_ENDPOINT}?table=conversations&offset=-1`, {
    headers: { Authorization: 'Bearer forged-not-a-real-session' },
  });
  await forged.body?.cancel();
  out(`[m5] reject: forged-session status=${forged.status} (expect 401)`);
  if (forged.status !== 401) {
    pass = false;
  }

  // --- no credential -> 401 ---
  const anon = await fetch(`${SHAPE_ENDPOINT}?table=conversations&offset=-1`);
  await anon.body?.cancel();
  out(`[m5] reject: no-credential status=${anon.status} (expect 401)`);
  if (anon.status !== 401) {
    pass = false;
  }

  // --- revoked session -> 401 ---
  store.revoke(bobSession);
  const revoked = await fetch(`${SHAPE_ENDPOINT}?table=conversations&offset=-1`, {
    headers: { Authorization: `Bearer ${bobSession}` },
  });
  await revoked.body?.cancel();
  out(`[m5] reject: revoked-session status=${revoked.status} (expect 401)`);
  if (revoked.status !== 401) {
    pass = false;
  }

  server.close();
  await closePool();

  out(
    pass
      ? '\nM5 PASS — identity comes from the validated session; forged/missing/revoked rejected; client-asserted header ignored'
      : '\nM5 FAIL'
  );
  process.exit(pass ? 0 : 1);
}

main().catch((error) => {
  process.stderr.write(`M5 crashed: ${String(error)}\n`);
  process.exit(1);
});
