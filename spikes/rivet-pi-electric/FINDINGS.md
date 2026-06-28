# Spike: Rivet + Pi + Postgres + Electric (M1–M4 gate)

Throwaway spike validating the substrate ADR
(`2026-06-27-rivet-postgres-electric-hatchet-substrate`) before rewriting the
003 plan. It now covers the full read/write vertical slice plus the read-path
security boundary:

- **M1** — one conversation = one Rivet actor running the unforked Pi loop,
  streaming tokens out over the actor WebSocket.
- **M2** — that actor's state survives a real cold restart (RocksDB).
- **M3** — the actor projects a conversation summary to **Postgres through the
  API (single writer)**, and **Electric** syncs that row to a second client
  live; the row + actor state survive a cold restart together.
- **M4** — an **identity-scoped gatekeeper** in front of Electric enforces a
  per-owner `where` clause + table/column allowlist server-side; a client cannot
  widen its view, even by sending its own `where`.

Effect-v4 client wrapping and Hatchet are intentionally **not** in this gate
(next gates).

## What runs

- `src/pi-turn.ts` — the unforked-Pi seam. Drives `runAgentLoop` from
  `@earendil-works/pi-agent-core` with a keyless faux provider
  (`createFauxCore` from `@earendil-works/pi-ai/providers/faux`). Pi is consumed
  as a published npm dependency (`0.80.2`); nothing patches it.
- `src/conversation-actor.ts` — a `rivetkit` actor. State = `{ systemPrompt, id,
  owner, messages, turnCount }`. `sendMessage` runs one Pi turn, `c.broadcast`s
  each `text_delta`, and (when an identity is bound via `setIdentity`) projects
  a summary row through the API. `getTranscript` reads persisted state.
- `src/db.ts` — the **only** module that talks to Postgres (`pg` pool, lazy).
- `src/api.ts` — the **single-writer** API seam (`upsertConversationSummary`).
  The actor imports this, never `db.ts`. In production this is `apps/api` over
  RPC; here it is an in-process function.
- `src/shape-client.ts` — the read-path client: `@electric-sql/client`
  `ShapeStream` over the `conversations` shape, materialized into a live map.
  Defaults to Electric directly (M3); accepts `url`/`headers` to route through
  the gatekeeper (M4).
- `src/proxy.ts` — the **identity-scoped gatekeeper** (`node:http`), trimmed from
  `backend/vendor/effect-api-layout/apps/electric-proxy`. Authenticates an
  identity, validates the table, forwards ONLY recognized Electric protocol
  params (`ELECTRIC_PROTOCOL_QUERY_PARAMS`), and **server-forces** the table, a
  column allowlist, and `where owner = $1` bound to the caller.
- `src/harness.ts` — in-process Rivet boot via `rivetkit/test` `setupTest`, with
  a runner-readiness retry (see findings).
- `src/m1.ts` / `src/m2.ts` / `src/m3.ts` / `src/m4.ts` — the milestone runners.
- `infra/docker-compose.yml` — PG 17 (logical replication) + Electric 1.5.1,
  isolated project/ports so it can't collide with the host's other Postgres.

## Versions (resolved)

| Package / image | Pinned | Resolved |
|---|---|---|
| `rivetkit` | `^2.2.2-rc.1` | **2.3.2** (past the RC the ADR worried about) |
| `@earendil-works/pi-agent-core` / `pi-ai` | `0.80.2` | 0.80.2 |
| `@electric-sql/client` | `1.5.13` | 1.5.13 |
| `pg` | `^8.13.0` | 8.22.0 |
| `electricsql/electric` (image) | `1.5.1` | 1.5.1 |
| `postgres` (image) | `17-alpine` | 17 |

## How to reproduce

```bash
cd spikes/rivet-pi-electric
bun install

# --- infra (M3 only): Postgres + Electric on loopback ports 5499 / 5599 ---
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

# M3a — raw single-writer write → Electric read-path sync (no actor)
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3a
# M3b — actor projects through the API; client A streams, client B syncs
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3b
# M3c — PG row + actor state survive a cold restart together
rm -rf .rivethome && mkdir -p .rivethome
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3c:seed
pgrep -f 'engine-cli-linux-x64-musl/rivet-engine start' | grep -vw "$$" | xargs -r kill
sleep 5   # PG + Electric keep running; only the Rivet engine restarts
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m3c:verify

# M4 — identity-scoped gatekeeper (no actor/engine; just PG + Electric + the proxy)
bun run m4
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
Cold restart with **PG + Electric left running, only the Rivet engine killed**
(verified: `6420 FREE before verify — engine truly down`):
- Electric replayed the persisted PG row (`turn_count=1`) to a fresh client.
- The actor replayed its transcript (`turnCount=1`, `messageCount=2`) from RocksDB.
- A follow-up turn continued to `turnCount=2`/`messageCount=4` and Electric
  synced the post-restart update (`turn_count=2`) live.

### M4 — PASS
Two owners (`alice`, `bob`) each own a row. With the gatekeeper in front of
Electric:
- **scope** — a client authenticating as alice synced **only** alice's row
  (`ownRow=true bobRow=false onlyOwnOwner=true rows=1`); bob's row never arrived.
- **sneak** — a client authenticating as alice but requesting `where owner='bob'`
  **still** saw nothing of bob's (`bobRow=false`): the proxy drops the client
  `where` and forces `owner = $1` server-side.
- **reject** — a request with no identity → **401**; a request for a
  non-allowlisted table (`secrets`) → **403**.

This is the boundary files-first could never enforce centrally: read access is
scoped per identity by the server, independent of what the client asks for.

## Operational findings (these matter for the ADR)

1. **rivetkit dev/test is not "pure in-process."** Even `setupTest` spawns the
   native engine binary, binds `127.0.0.1:6420`, and persists state to an
   on-disk **RocksDB** under `$HOME/.rivetkit/var/engine/db`.
2. **Sandbox needs a writable `HOME`** for the engine (defaults to `/root/.rivetkit`).
3. **The engine child is orphaned on exit** and holds the RocksDB `LOCK` + port
   6420. Production needs explicit engine lifecycle management.
4. **Startup race: `no_runner_config_configured`** — first actor call can fire
   before the runner pool registers; worked around with a readiness retry.
5. **Durability requires a stable runner version** (`RIVET_ENVOY_VERSION`), else
   `actor_ready_timeout`. Mirrors the reference's `configureRunnerPool` versioning.
6. **Postgres durability is independent of the Rivet engine.** Because PG runs as
   its own service, the conversation row survives an engine restart for free;
   Electric re-syncs it to clients on reconnect. This is exactly why the
   queryable record lives in PG, not in the actor.
7. **Electric's `message.key` is structured, not the PK** (e.g.
   `"public"."conversations"/"<id>"`). Materialize by the row's own `id`
   (`message.value.id`), and merge partial update values (default `replica`
   sends only PK + changed columns).
8. **`pgrep -f '...rivet-engine start'` self-matches the shell** running it (the
   pattern is in your own argv), so a naive `pkill`/`xargs kill` kills the shell
   (or, with a multi-line PID string, zsh's no-word-split throws `illegal pid`).
   Exclude the current shell: `pgrep -f ... | grep -vw "$$" | xargs -r kill`.
9. **The gatekeeper's security rests on forwarding an allowlist, not a denylist.**
   The proxy copies ONLY `ELECTRIC_PROTOCOL_QUERY_PARAMS` (offset/handle/live/
   cursor/cache-buster) from the client, then sets `table`/`columns`/`where`/
   `params` itself. Because `where`/`columns`/`table` are not protocol params,
   any client-supplied versions are silently dropped — there's no way for a
   client to inject a broader scope. Forward the Electric protocol param list as
   it ships in `@electric-sql/client`; don't hand-maintain it.
10. **Forward the client's disconnect to the upstream.** Electric long-polls on
   `live=true`; without wiring the request `close` event into an `AbortController`
   on the upstream `fetch`, a client closing its `ShapeStream` leaves a dangling
   long-poll against Electric per reconnect.

## Implication for the next step

The full read/write substrate is structurally sound and the read path is safe to
expose to untrusted clients: single-writer actor → API → Postgres → Electric →
**identity-scoped gatekeeper** → second client, all surviving a cold restart.
What's still unproven / deliberately deferred before the 003 rewrite:

- **Engine lifecycle + runner-pool versioning** must move off the `setupTest`
  harness onto the reference's `serverless.configureRunnerPool` shape.
- **Real identity** behind the gatekeeper: the spike trusts an `x-spike-user`
  header; production must validate the session cookie (Tailscale/profile) and
  derive the owner from it, not from a client-controlled header.
- **Effect v4 wrapping** of the Rivet + Electric + PG clients (`@clients/*`),
  and **Hatchet** for system-level durable work — later gates.
