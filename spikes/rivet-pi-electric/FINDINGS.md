# Spike: Rivet + Pi (M1/M2 gate)

Throwaway spike validating the substrate ADR
(`2026-06-27-rivet-postgres-electric-hatchet-substrate`) before rewriting the
003 plan. Scope of this gate: **one conversation = one Rivet actor running the
unforked Pi agent loop**, streaming tokens out (M1) and surviving a real restart
(M2). The Postgres + Electric half is intentionally NOT in this gate.

## What runs

- `src/pi-turn.ts` — the unforked-Pi seam. Drives `runAgentLoop` from
  `@earendil-works/pi-agent-core` with a keyless faux provider
  (`createFauxCore` from `@earendil-works/pi-ai/providers/faux`). Pi is consumed
  as a published npm dependency (`0.80.2`); nothing patches it.
- `src/conversation-actor.ts` — a `rivetkit` actor. State = `{ systemPrompt,
  messages, turnCount }`. `sendMessage` runs one Pi turn and `c.broadcast`s each
  `text_delta`; `getTranscript` reads persisted state.
- `src/harness.ts` — in-process boot via `rivetkit/test` `setupTest`, driven
  from a plain script with a stub test context, plus a runner-readiness retry
  (see findings).
- `src/m1.ts` / `src/m2.ts` — the two milestone runners.

## Versions (resolved)

| Package | Pinned | Resolved |
|---|---|---|
| `rivetkit` | `^2.2.2-rc.1` | **2.3.2** (past the RC the ADR worried about) |
| `@earendil-works/pi-agent-core` | `0.80.2` | 0.80.2 |
| `@earendil-works/pi-ai` | `0.80.2` | 0.80.2 |

## How to reproduce

The native engine writes under `$HOME/.rivetkit`, so point `HOME` at a writable
dir and pin a stable runner version. Exactly one engine may run at a time.

```bash
cd spikes/rivet-pi-electric
bun install

# M1 — Pi-in-actor streaming
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m1

# M2 — durability across a real cold restart
rm -rf .rivethome && mkdir -p .rivethome
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m2:seed
pkill -f 'rivet-engine start'; sleep 5        # kill the orphaned engine
RIVET_ENVOY_VERSION=1 HOME="$PWD/.rivethome" bun run m2:verify
```

## Results

### M1 — PASS

The unforked Pi agent loop ran inside the Rivet actor. 22 `text_delta`
broadcasts reached the connected client live; the returned `assistantText`
equalled the concatenated stream; transcript persisted 2 messages
(user + assistant).

### M2 — PASS (with one hard requirement)

Cold restart = both the JS process and the native engine were terminated, then a
fresh process + fresh engine opened the **same on-disk RocksDB**.

- Seed wrote `turnCount=1`, `messageCount=2`.
- After restart, verify **replayed** `turnCount=1`, `messageCount=2` from disk,
  then **continued** to `turnCount=2`, `messageCount=4`.

## Operational findings (these matter for the ADR)

1. **rivetkit dev/test is not "pure in-process."** Even `setupTest` spawns the
   native engine binary (`@rivetkit/engine-cli-linux-x64-musl/rivet-engine`),
   binds a local port (`127.0.0.1:6420`), and persists actor state to an on-disk
   **RocksDB** under `$HOME/.rivetkit/var/engine/db`. Heavier than the ADR
   assumed, but it is what makes durability real.
2. **Sandbox needs a writable `HOME`.** The engine defaults its data dir to
   `/root/.rivetkit`; the sandbox blocks that. Redirect `HOME` (or otherwise set
   the data dir) to a writable path.
3. **The engine child is orphaned on exit.** `registry.shutdown()` tears down the
   JS runtime/runner but does **not** reap the spawned engine. Left running, it
   holds the RocksDB `LOCK` and blocks the next start. Production needs explicit
   engine lifecycle management.
4. **Startup race: `no_runner_config_configured`.** `setupTest` waits for engine
   `/metadata` but not for the in-process runner pool to register, so the first
   actor call can fire too early. Worked around with a readiness retry in
   `harness.ts`.
5. **Durability requires a stable runner version.** Without `RIVET_ENVOY_VERSION`
   set, a persisted actor cannot be re-placed on the new (differently-identified)
   runner after restart — it fails with `actor_ready_timeout`. Setting a stable
   `RIVET_ENVOY_VERSION` fixed it. This mirrors the reference project's
   `configureRunnerPool` + versioning; the production runner pool config (not the
   test harness) is the real durable path.

## Implication for the next step

Durability is structurally sound (single-writer actor → on-disk RocksDB →
survives cold restart). Before the Postgres/Electric half, the production wiring
must (a) own the engine lifecycle and (b) pin a stable runner version. Consider
adopting the reference's `serverless.configureRunnerPool` shape rather than
`setupTest` for any further durability/integration work.
