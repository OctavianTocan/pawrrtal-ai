# Quickstart — Validating the Overhaul Incrementally

This program plan ships no single deliverable; it is validated **slice by slice** as each split spec lands. Below are the runnable validation gates the program relies on, plus how to prove each foundation works. (No implementation code here — that's per split spec's `tasks.md`.)

## Prerequisites

- Repo at `/mnt/HC_Volume_105512717/dev/pawrrtal`; Python backend on `:8000`, Effect strangler on `:8001` (`just dev` / `bun dev.ts`; opt out of TS with `PAWRRTAL_SKIP_TS_API=1`).
- Effect signatures verified against `backend/vendor/effect-smol` (never guessed). Style mirrored from `../use-agy` **code** (not its docs).

## Gate 0 — Fix the strangler test gate (do first)

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
- **Sandbox**: agent-generated code runs under gVisor by default.
  ```bash
  docker run --runtime=runsc <agent-image> sh -c 'cat /proc/version'   # gVisor kernel, not host
  ```

## Gate 4 — End-to-end via `paw` + the visual harness

- `cd backend && uv run paw verify chat-roundtrip --json` (or the Effect `paw` once rewritten) — exercises the real HTTP/SSE surface a UI would.
- The **visual harness** (spec 002) captures the real Telegram/web rendering and compares it to the golden references — the rendering gate for any surface story.

## Architecture gates (every slice)

```bash
just sentrux          # package/import boundaries (core ⇏ optional)
just check            # biome + ruff
```

The core must compile and test with **zero providers, zero channels, zero tools** installed — the structural proof the kernel stays thin.
