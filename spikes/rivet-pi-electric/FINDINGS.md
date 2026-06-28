# Spike: Rivet + Pi + Postgres + Electric + Hatchet (M1–M9)

Throwaway spike validating the substrate ADR
(`2026-06-27-rivet-postgres-electric-hatchet-substrate`) before rewriting the
003 plan. It now covers the full read/write vertical slice, the read-path
security boundary, the production engine lifecycle, the Effect-v4 client
wrapping, durable background work, and the actor's own session-scoped scheduler:

- **M1** — one conversation = one Rivet actor running the unforked Pi loop,
  streaming tokens out over the actor WebSocket.
- **M2** — that actor's state survives a real cold restart (RocksDB).
- **M3** — the actor projects a conversation summary to **Postgres through the
  API (single writer)**, and **Electric** syncs that row to a second client
  live; the row + actor state survive a cold restart together.
- **M4** — an **identity-scoped gatekeeper** in front of Electric enforces a
  per-owner `where` clause + table/column allowlist server-side; a client cannot
  widen its view, even by sending its own `where`.
- **M5** — identity behind the gatekeeper comes from a **trusted session
  authority**, not a client-asserted header; forged/missing/revoked sessions are
  rejected.
- **M6** — the actor runs under the **production standalone engine shape**
  (`startEngine` + pinned `engineVersion`/`envoy.version` + `registry.start()`),
  off the `setupTest` harness, and survives a real cold restart this runner
  performs itself.
- **M7** — the PG / Electric / Rivet clients are wrapped as **Effect v4 services
  + layers** and exercised through one composed runtime.
- **M8** — durable system work runs on **Hatchet** (Postgres-backed queue),
  survives a worker restart, and projects through the same single-writer seam.
- **M9** — the actor's **own scheduler** (`c.schedule.after(...)` → a named
  action) is durable: a per-session wake registered before a real cold restart
  still fires (mutating state) after the actor rehydrates, with no client
  invoking it. This is the session-scoped-timer half of the ADR's RC risk.

## What runs

- `src/pi-turn.ts` — the unforked-Pi seam. Drives `runAgentLoop` from
  `@earendil-works/pi-agent-core` with a keyless faux provider
  (`createFauxCore` from `@earendil-works/pi-ai/providers/faux`). Pi is consumed
  as a published npm dependency (`0.80.2`); nothing patches it.
- `src/conversation-actor.ts` — a `rivetkit` actor. State = `{ systemPrompt, id,
  owner, messages, turnCount, wakeCount, lastWakeLabel }`. `sendMessage` runs one
  Pi turn, `c.broadcast`s each `text_delta`, and (when an identity is bound via
  `setIdentity`) projects a summary row through the API. `getTranscript` reads
  persisted state. `scheduleWake` registers a durable per-session wake via
  `c.schedule.after`, `fireWake` is the scheduler-only callback that mutates
  state, `getWakes` reads the wake counters (M9).
- `src/db.ts` — the **only** module that talks to Postgres (`pg` pool, lazy).
- `src/api.ts` — the **single-writer** API seam (`upsertConversationSummary`).
  The actor imports this, never `db.ts`. In production this is `apps/api` over
  RPC; here it is an in-process function.
- `src/shape-client.ts` — the read-path client: `@electric-sql/client`
  `ShapeStream` over the `conversations` shape, materialized into a live map.
  Defaults to Electric directly (M3); accepts `url`/`headers` to route through
  the gatekeeper (M4/M5).
- `src/proxy.ts` — the **identity-scoped gatekeeper** (`node:http`), trimmed from
  `backend/vendor/effect-api-layout/apps/electric-proxy`. Pluggable `ProxyAuth`:
  `headerAuth` (M4, trusts `x-spike-user`) and `sessionAuth` (M5, resolves a
  session through the trusted store). Validates the table, forwards ONLY
  recognized Electric protocol params (`ELECTRIC_PROTOCOL_QUERY_PARAMS`), and
  **server-forces** the table, a column allowlist, and `where owner = $1`.
- `src/session-store.ts` — the trusted-authority stand-in for M5 (an in-memory
  `/users/me`): `create` / `lookup` / `revoke` over opaque session ids.
- `src/server.ts` — the **standalone actor server** (M6/M7): `setup({ ...,
  startEngine: true, enginePort, engineVersion, envoy: { version } })` +
  `registry.start()`. The production shape, off `setupTest`.
- `src/server-control.ts` — OS-level lifecycle for `src/server.ts` (spawn, stop
  both the server child AND the engine, port-free polling, readiness probe).
  Shared by M6 and M7.
- `src/effect/` — the M7 Effect-v4 wrapping: `Pg` (scoped pool via `Layer.effect`
  + `acquireRelease`), `Conversations` (the API seam, depends on `Pg`),
  `Electric` (the shape via `acquireUseRelease`), `Rivet` (the client, layer
  parameterized by endpoint), and an `index.ts` barrel.
- `src/hatchet/workflow.ts` — the Hatchet client + the one durable task
  (`project-conversation-summary`), which projects through the SAME
  `upsertConversationSummary` seam. `src/hatchet/worker.ts` — the standalone
  worker process (run as a child so M8 can kill it).
- `src/m1.ts` … `src/m9.ts` — the milestone runners.
- `infra/docker-compose.yml` — PG 17 (logical replication) + Electric 1.5.1,
  isolated project/ports (`:5499` / `:5599`).
- `infra/hatchet-compose.yml` — `hatchet-lite` on its OWN Postgres (`:5502`),
  with a one-shot `hatchet-setup` that mints an API token to
  `infra/hatchet-creds/api-token`. Host ports remapped to **gRPC :7079 / API
  :8899** (see findings).

## Versions (resolved)

| Package / image | Pinned | Resolved |
|---|---|---|
| `rivetkit` | `^2.2.2-rc.1` | **2.3.2** (past the RC the ADR worried about) |
| `@earendil-works/pi-agent-core` / `pi-ai` | `0.80.2` | 0.80.2 |
| `@electric-sql/client` | `1.5.13` | 1.5.13 |
| `effect` | `4.0.0-beta.74` | 4.0.0-beta.74 |
| `@hatchet-dev/typescript-sdk` | `^1.22.0` | **1.24.3** |
| `pg` | `^8.13.0` | 8.22.0 |
| `electricsql/electric` (image) | `1.5.1` | 1.5.1 |
| `hatchet-dev/hatchet-lite` (image) | `latest` | latest |
| `postgres` (image) | `17-alpine` | 17 |

## How to reproduce

```bash
cd spikes/rivet-pi-electric
bun install

# --- app infra (M3–M8 read/write path): Postgres + Electric on 5499 / 5599 ---
docker compose -f infra/docker-compose.yml up -d
# tear down later: docker compose -f infra/docker-compose.yml down -v

# M1 — Pi-in-actor streaming
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m1

# M2 — actor durability across a real cold restart
rm -rf .rivethome && mkdir -p .rivethome
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m2:seed
# kill ONLY the spike engine, excluding this shell (pgrep self-matches the pattern!)
pgrep -f 'engine-cli-linux-x64-musl/rivet-engine start' | grep -vw "$$" | xargs -r kill
sleep 5
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m2:verify

# M3a/b/c — single-writer → Electric read-path sync; survives a cold restart
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3a
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3b
rm -rf .rivethome && mkdir -p .rivethome
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3c:seed
pgrep -f 'engine-cli-linux-x64-musl/rivet-engine start' | grep -vw "$$" | xargs -r kill
sleep 5
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3c:verify

# M4 — identity-scoped gatekeeper (trusts the x-spike-user header)
bun run m4

# M5 — identity from a trusted session authority (header no longer trusted)
bun run m5

# M6 / M7 / M9 — standalone engine server on :6420. Ensure :6420 is FREE first
# (a stale engine breaks the boot with no_runner_config_configured — see findings):
pgrep -x rivet-engine | xargs -r kill ; sleep 3
RIVET_ENVOY_VERSION=1 bun run m6   # cold-restart durability, off the harness
RIVET_ENVOY_VERSION=1 bun run m7   # PG/Electric/Rivet wrapped as Effect v4 layers
pgrep -x rivet-engine | xargs -r kill ; sleep 3
RIVET_ENVOY_VERSION=1 bun run m9   # actor scheduler/alarm durability across a cold restart

# M8 — Hatchet durable background work surviving a worker restart
docker compose -f infra/hatchet-compose.yml up -d   # mints infra/hatchet-creds/api-token
bun run m8
docker compose -f infra/hatchet-compose.yml down -v
```

## Results

### M1 — PASS
The unforked Pi loop ran inside the Rivet actor. ~22 `text_delta` broadcasts
reached the client live; returned `assistantText` equalled the concatenated
stream; transcript persisted 2 messages.

### M2 — PASS
Cold restart (JS process + native engine both terminated) → fresh process +
engine opened the same on-disk RocksDB. Seed `turnCount=1`/`messageCount=2`;
verify replayed it and continued to `turnCount=2`/`messageCount=4`. Requires a
stable `RIVET_ENVOY_VERSION` (see findings).

### M3a — PASS
The API wrote a `conversations` row; a separate `@electric-sql/client` client
saw the **insert** (`turn_count=1`) then the **update** (`turn_count=2`) live,
with no polling.

### M3b — PASS
A Pi turn streamed 23 deltas to client A (actor WS) **and** the projected
summary row (`owner=bob`, `turn_count=1`, title set) appeared in client B
(Electric) — the ADR's combined acceptance criterion. The actor reached PG only
through `api.ts`; it never imports `db.ts` (single writer, structural).

### M3c — PASS
Cold restart with **PG + Electric left running, only the Rivet engine killed**:
Electric replayed the persisted PG row, the actor replayed its transcript from
RocksDB, and a follow-up turn continued + synced live.

### M4 — PASS
Two owners (`alice`, `bob`) each own a row. With the gatekeeper in front of
Electric: **scope** (alice synced only alice's row), **sneak** (alice requesting
`where owner='bob'` still saw nothing — the proxy drops the client `where`),
**reject** (no identity → 401; non-allowlisted table → 403).

### M5 — PASS
Same two owners, but the proxy resolves identity through the trusted session
store (`sessionAuth`), not a header:
- **session-scope** — a validated session for alice synced **only** alice's row
  (`ownRow=true bobRow=false rows=1`).
- **header-not-trusted** — alice's session **plus** `x-spike-user: bob` still
  yielded only alice's row (`bobRow=false`): the asserted header is ignored.
- **reject** — forged session → **401**, no credential → **401**, revoked
  session → **401**.

This is the production-shaped boundary: the client never names who it is; the
server derives the owner from a credential it minted.

### M6 — PASS
The actor booted under the **standalone production shape** (`src/server.ts`:
`startEngine` + pinned `engineVersion=1` / `envoy.version=1` + `registry.start()`),
connected via an external `createClient`, and survived a real cold restart this
runner performed itself (kill the server **and** the engine, wait for `:6420` to
free, reboot): seed `turnCount=1`/`transcriptLength=2` → replay
`turnCount=1`/`messageCount=2` → continue `turnCount=2`/`transcriptLength=4`.
Deterministic across repeated runs once the pre-kill settle window was added
(see findings #12).

### M7 — PASS
Each raw client became an Effect v4 `Service` + `Layer` (`Pg` as a scoped pool
via `Layer.effect` + `acquireRelease`; `Electric` and `Rivet` as `Layer.succeed`),
composed with `Layer.mergeAll`, run once via `Effect.runPromise`:
- **pg+electric** — wrote a summary through the wrapped `Conversations` seam
  (over the scoped pool) and read it back through the wrapped Electric shape
  (`row.owner` matched, `turn_count=1`).
- **rivet** — ran a turn and read the transcript through the wrapped client
  against the standalone server (`turn=1`, `transcript.turnCount=1`,
  `messageCount=2`).

### M8 — PASS
Hatchet (`hatchet-lite` on its own Postgres) ran the durable
`project-conversation-summary` task, which writes through the SAME
`upsertConversationSummary` seam the actor uses:
- **baseline** — worker up → task A ran end-to-end → row A in the app PG.
- **down** — SIGKILL the worker, then enqueue task B while nothing serves it; B
  was **not** projected (`B before restart=false`) — it sat in Hatchet's PG queue.
- **restart** — bring the worker back; it picked the **same run id** off the
  durable queue and projected row B (`B after restart=true`).

Durable system work survives the worker dying and lands through the single
writer — no work is lost, and Hatchet never gets its own write path to the DB.

### M9 — PASS
The actor scheduled a per-session wake via its own scheduler
(`c.schedule.after(20s, 'fireWake', label)`), under the same standalone engine
shape as M6. `wakeCount=0` before the cold restart (the wake had not fired); the
runner then killed the server **and** the engine, waited for `:6420` to free,
and rebooted. After rehydration the scheduler fired the wake **unaided** (no
client called `fireWake`): `wakeCount=1`, `lastWakeLabel` matched. Deterministic
across repeated runs. Because the engine reboot (boot + runner registration)
itself takes ~20-30s, the wake's fire time elapses during downtime and the wake
**catches up on rehydration** — the stronger durability property (a missed
session timer is not dropped). This is the alarm half of the ADR's RC risk that
M2/M6 (state) left open, and it's what lets session-scoped timers live on the
actor instead of Hatchet.

## Operational findings (these matter for the ADR)

1. **rivetkit dev/test is not "pure in-process."** Even `setupTest` spawns the
   native engine binary, binds `127.0.0.1:6420`, and persists state to an
   on-disk **RocksDB** under `$HOME/.rivetkit/var/engine/db`.
2. **Sandbox needs a writable `HOME`** for the engine (defaults to `/root/.rivetkit`).
3. **The engine child is orphaned on exit** and holds the RocksDB `LOCK` + port
   6420. Production needs explicit engine lifecycle management. (See #11 for how
   this bites the standalone server.)
4. **Startup race: `no_runner_config_configured`** — first actor call can fire
   before the runner pool registers; worked around with a readiness retry.
5. **Durability requires a stable runner version** (`RIVET_ENVOY_VERSION` /
   pinned `envoy.version`), else `actor_ready_timeout`. Mirrors the reference's
   runner-pool versioning.
6. **Postgres durability is independent of the Rivet engine.** Because PG runs as
   its own service, the conversation row survives an engine restart for free;
   Electric re-syncs it on reconnect. This is why the queryable record lives in
   PG, not in the actor.
7. **Electric's `message.key` is structured, not the PK** (e.g.
   `"public"."conversations"/"<id>"`). Materialize by the row's own `id`, and
   merge partial update values (default `replica` sends only PK + changed cols).
8. **`pgrep -f '...rivet-engine start'` self-matches the shell** running it, so a
   naive `pkill`/`xargs kill` kills the shell. Exclude the current shell:
   `pgrep -f ... | grep -vw "$$" | xargs -r kill`. (`pkill -x rivet-engine`
   matches the engine by exact name and avoids this.)
9. **The gatekeeper's security rests on forwarding an allowlist, not a denylist.**
   The proxy copies ONLY `ELECTRIC_PROTOCOL_QUERY_PARAMS`, then sets
   `table`/`columns`/`where`/`params` itself. Client-supplied `where`/`columns`/
   `table` are silently dropped. Forward the protocol param list as it ships in
   `@electric-sql/client`; don't hand-maintain it.
10. **Forward the client's disconnect to the upstream.** Electric long-polls on
    `live=true`; wire the request `close` event into an `AbortController` on the
    upstream `fetch`, or a closing `ShapeStream` leaks a dangling long-poll.
11. **A stale engine on `:6420` silently hijacks the next standalone run.** The
    orphaned engine (#3) keeps the port; the next `src/server.ts` attaches to it
    instead of booting its own, and because that engine has no runner config for
    the new boot, every actor call fails `no_runner_config_configured` until
    `waitForReady` times out. The standalone lifecycle must ensure `:6420` is
    free (kill stale `rivet-engine`) before boot, not only between restarts.
12. **Actor state persists to the engine asynchronously w.r.t. the turn.** A turn
    resolving means in-memory state changed, not that the engine flushed it. A
    hard kill of the envoy *immediately* after a turn can drop the last write
    before it reaches RocksDB → the cold restart replays empty state (observed as
    a flaky M6 `replay turnCount=0`). Durability is of **committed** state: settle
    briefly (or shut down gracefully) before a cold kill. M2/M3c masked this with
    a `sleep 5`; M6 makes the settle explicit.
13. **Effect v4 has no `Layer.scoped`.** `Layer.effect` accepts a scoped effect
    (e.g. one built from `Effect.acquireRelease`) and discharges the `Scope`
    itself — that is the idiom for a pooled/closable client (the `Pg` pool).
14. **Hatchet task I/O must be `type` aliases, not `interface`s.** The SDK
    constrains inputs/outputs to `JsonObject` (`{ [k: string]: JsonValue }`).
    Object-literal `type` aliases get an implicit string index signature and
    satisfy it; `interface`s don't (they're open to augmentation) and fail to
    typecheck.
15. **The Hatchet API token embeds the gRPC broadcast address.** When the host
    already runs another Hatchet (this VPS does, on `7077`/`8888`), remapping the
    spike's host ports is not enough — `SERVER_GRPC_BROADCAST_ADDRESS` must equal
    the host port you actually expose (`localhost:7079`), or the freshly minted
    token points the SDK at the OTHER Hatchet. The in-container internal client
    still uses the container port (`7077`).
16. **Hatchet durability is the queue, not the worker.** A run enqueued while no
    worker is alive sits in Hatchet's Postgres and is delivered to the next
    worker that registers the task — the restarted worker picked up the *same run
    id*. The worker is stateless; the durability lives in Hatchet's PG.
17. **Actor schedules are durable AND catch up on rehydration.** A wake set with
    `c.schedule.after(ms, 'action', ...args)` persists alongside actor state;
    after a cold restart the actor fires it on its own, with no client connected.
    Because the engine reboot alone takes ~20-30s, the wake's fire time routinely
    elapses *during downtime* — and it still fires when the actor rehydrates
    (a missed session timer is caught up, not dropped). This is the durability
    that lets session-scoped timers live on the actor (per the ADR scope rule),
    leaving Hatchet for system-level work. Same async-persist caveat as #12: the
    `schedule` call returning is not the same as it being on disk — settle (or
    shut down gracefully) before a hard kill.

## Implication for the next step

Every piece of the substrate ADR is now proven end-to-end and the spike has
nothing left deliberately deferred:

- **read/write vertical slice** — single-writer actor → API → Postgres →
  Electric → second client, surviving a cold restart (M1–M3).
- **read-path security** — an identity-scoped gatekeeper backed by a trusted
  session authority; clients cannot name themselves or widen scope (M4–M5).
- **engine lifecycle** — the production standalone shape (`startEngine` + pinned
  runner version), durable across a self-driven cold restart, off the test
  harness (M6).
- **Effect v4 wrapping** — PG, Electric, and Rivet as services + layers in one
  composed runtime (M7).
- **durable system work** — Hatchet (Postgres-backed) surviving a worker restart
  and projecting through the single writer (M8).
- **session-scoped durable timers** — the actor's own scheduler firing a wake
  after a cold restart (catching up a missed fire on rehydration), which is what
  keeps per-session time on the actor and off Hatchet (M9).

Both halves of the ADR's headline RC risk — **state** durability (M2/M3c/M6)
**and** **alarm** durability (M9) — are now proven for `rivetkit` 2.3.2.

The substrate is ready to graduate from a throwaway spike into the 003 plan
rewrite. The findings above (especially #11 engine-port hygiene, #12/#17
async-persist settle, #15 Hatchet broadcast address) are the operational sharp
edges the real `apps/api` + engine-lifecycle code must handle deliberately
rather than rediscover.
