# Quickstart — Validating the Overhaul Incrementally

This program plan ships no single deliverable; it is validated **slice by slice** as each split spec lands. Below are the runnable validation gates the program relies on, plus how to prove each foundation works. (No implementation code here — that's per split spec's `tasks.md`.)

## Prerequisites

- Repo at `/mnt/work/code/personal/pawrrtal`; Python backend on `:8000`, Effect strangler on `:8001` (`just dev` / `bun dev.ts`; opt out of TS with `PAWRRTAL_SKIP_TS_API=1`).
- Effect signatures verified against `backend/vendor/effect-smol` (never guessed). Style mirrored from `../use-agy` **code** (not its docs).

## Gate 0A — Agent-native setup/customization spine (do first)

The first visible slice teaches coding agents how to set up, recover, and customize Pawrrtal without hidden maintainer context. Prove the split spec by running the documented path from a fresh checkout or clean worktree:

```bash
# Names are allowed to change in the split spec; the gate is the behavior:
paw setup --dry-run --json       # reports prerequisites, config files, secret refs, and first-run actions
paw doctor --setup --json        # detects an interrupted setup and prints the exact resume command
paw doctor --config --json       # validates schema-backed config files and rejects plaintext secrets
```

Done when: a coding agent can follow the root README/AGENTS/skills path to bootstrap the repo, intentionally interrupt and resume setup, wire one requested capability through a skills-on-demand path, validate typed config, and produce a first verified message. Pawrrtal keeps config files; the gate is that they are typed, generated/example-backed, and validated.

## Gate 0B — Fix the strangler test gate

The current backend-ts test gate is **falsely green**. Prove the fix:

```bash
cd backend-ts
bun run --filter '@pawrrtal/*' typecheck      # must stay: both packages exit 0
# Expected AFTER fix: @effect/vitest it.effect suites actually COLLECT and run
#   (today: "No test suite found" / 0 tests, masked by --passWithNoTests)
# Expected AFTER fix: one test tree (Modules/** OR unit/**), not two divergent ones
```

Done when: suites run real assertions, `--passWithNoTests` removed, duplicate tree de-duplicated.

## Gate 1 — Shared contracts hold

For each contract in [contracts/](./contracts/), the validation is a conformance check, not a feature:

- **message-parts**: fold a recorded PartDelta stream server-side and client-side → byte-identical `parts[]` (the live-vs-rehydrated invariant).
- **provider-taxonomy**: each provider exposes a `CapabilityManifest`; the picker never offers tools a `none` provider can't enforce.
- **session-record**: a resumed conversation has exactly one `context_owner`; no double/zero history replay.
- **gateway**: an external OpenAI-compatible request to Pawrrtal returns a stream that projects the same `parts[]` a native channel renders.

## Gate 2 — A migrated slice reaches parity (strangler)

Per slice (Projects is the template), prove `:8001` matches `:8000`:

```bash
cd backend-ts && bun run --filter '@pawrrtal/*' typecheck
# Drive the same endpoint on both backends and diff the response (status-code parity first):
curl -s -b "session_token=$T" localhost:8000/api/v1/projects | jq .
curl -s -b "session_token=$T" localhost:8001/api/v1/projects | jq .
# Effect handler must use `yield* CurrentUser`, not STUB_USER_ID, before a slice counts as done.
```

Done when: the slice typechecks, passes its `@effect/vitest` suite, and reaches response parity with Python (status codes; body-shape adapter only if the frontend depends on the body).

## Gate 3 — Self-hosted substrates

- **Secrets**: no plaintext anywhere; every surface resolves via self-hosted Infisical.
  ```bash
  rg -n "API_KEY=|SECRET=|TOKEN=" --glob '!**/*.example' .   # expect: no real secrets
  infisical run --domain=$INFISICAL_DOMAIN --projectId=… --env=dev -- just dev   # app boots with injected env
  ```
- **Sandbox**: agent-generated code runs under the **`local-confined`** default (CWD-confined + network-off via OS primitives, no container); heavier tiers are opt-in.
  ```bash
  # default tier: a write outside the confined CWD is refused, and shell/code has no network
  # opt-in gVisor tier (only when a conversation selects docker-gvisor):
  docker run --runtime=runsc <agent-image> sh -c 'cat /proc/version'   # gVisor kernel, not host
  ```

## Gate 4 — Persistence substrate (Rivet · Postgres · Electric · Hatchet)

The substrate is validated end-to-end by the `spikes/rivet-pi-electric` M1–M9 spike (`rivetkit` 2.3.2). Each slice that touches persistence re-proves the relevant leg:

- **Single-writer projection + live sync**: a turn streams tokens over the conversation actor's WebSocket **and** the conversation's metadata row, written **only by the API**, appears in a second client via Electric — and both survive an actor cold restart. (Spike M1–M3.)
- **Read-path scoping**: a client cannot widen its Electric view — the gatekeeper server-forces `where owner = <id>` + a table/column allowlist, with identity from a **trusted session authority**, not a client header. (M4–M5.)
- **Actor durability**: actor state **and** a per-session scheduled wake survive a real cold restart (the wake catches up on rehydration). (M2/M6/M9.)
- **Durable system work**: a Hatchet task enqueued while the worker is down lands when a worker returns, through the same single-writer seam. (M8.)

```bash
# spike reproduction (throwaway slice; the real apps/api wires the same shape):
cd spikes/rivet-pi-electric && bun install
docker compose -f infra/docker-compose.yml up -d   # Postgres 17 + Electric on :5499 / :5599
pgrep -x rivet-engine | xargs -r kill ; sleep 3     # engine-port hygiene before boot (FINDINGS #11)
RIVET_ENVOY_VERSION=1 bun run m6                     # cold-restart durability, off the harness
RIVET_ENVOY_VERSION=1 bun run m9                     # session-scoped scheduled wake survives a cold restart
```

Done when: the slice's persistence leg matches the spike's proven behavior — single writer per store, identity-scoped reads, durable actor state + schedules, durable Hatchet queue.

## Gate 5 — End-to-end via `paw` + the visual harness

- `cd backend && uv run paw verify chat-roundtrip --json` (or the Effect `paw` once rewritten) — exercises the real HTTP/SSE surface a UI would.
- The **visual harness** (spec 002) captures the real Telegram/web rendering and compares it to the golden references — the rendering gate for any surface story.

## Architecture gates (every slice)

```bash
just sentrux          # package/import boundaries (core ⇏ optional)
just check            # biome + ruff
```

The core must compile and test with **zero providers, zero channels, zero tools** installed — the structural proof the kernel stays thin.
