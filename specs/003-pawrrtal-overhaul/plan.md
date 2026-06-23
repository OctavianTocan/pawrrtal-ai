# Implementation Plan: Pawrrtal Platform Overhaul — Program / Architecture Plan

**Branch**: `003-pawrrtal-overhaul` | **Date**: 2026-06-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-pawrrtal-overhaul/spec.md`

> **Plan altitude.** `003` is an umbrella spec, so this is a **program / architecture plan**, not a single buildable implementation plan. It resolves the *cross-cutting* research (Phase 0) and locks the *shared design* every story inherits (Phase 1): the four shared contracts, the thin-core package decomposition, the self-hosted substrates, and the incremental migration sequence. **Per-feature task lists (`/speckit-tasks`) and implementation happen per split spec** — see Complexity Tracking and the Sequencing Roadmap. This keeps the constitution's reviewable-increments principle intact: this plan ships nothing; it makes the splits coherent.

## Summary

Converge Pawrrtal onto a **tiny Effect-TS kernel + a small set of packages (kernel · `api-core` contracts · host) + capabilities as discovered files/data**, fronted by **one normalized gateway** that drives any model or full agent CLI, with **sandboxed execution**, **self-hosted secrets**, and the **removal** of the permission/budget/telemetry/workspace systems — migrating off Python via the **existing `backend-ts/` strangler** (Python `:8000` canonical, Effect `:8001` coexisting behind stable HTTP contracts). The technical approach is **continuity, not greenfield**: `backend-ts/` already encodes the `api-core`(contract)/`apps/api`(runtime) split, the Service/Repo/Body/Live patterns, Effect SQL, and cookie auth — with exactly one of ~21 Python route groups (Projects) ported. This plan locks the contracts and the decomposition so each split spec extends that one proven slice instead of re-deciding the architecture.

## Technical Context

**Language/Version**: End-state **TypeScript on Effect v4 (effect-smol)**; today Python 3.13/FastAPI (strangler coexistence). Frontend Next.js 15/React 19; mobile React Native/Expo (Story 15). *Version reconciliation needed:* `backend-ts` pins `effect@4.0.0-beta.74`; `../use-agy` pins `beta.85` — diff vendored revisions before copying signatures.

**Primary Dependencies**: `effect` v4 unstable surfaces (`effect/unstable/httpapi`, `effect/unstable/http`, `effect/unstable/sql`), `@effect/platform-bun`, `@effect/sql-sqlite-bun` (dev) / `@effect/sql-pg` (prod), `@effect/vitest`; Bun; Biome. Source-of-truth for every signature = `backend/vendor/effect-smol` submodule (never guess an API).

**Storage**: Postgres (prod, Railway) / SQLite (dev) behind a **driver-swappable `SqlClient` layer**. **Alembic remains the single schema authority** for the whole migration; Effect reads Alembic-managed tables, owns no migrations. Persistence = **Effect SQL (`@effect/sql`), not Drizzle**.

**Testing**: `@effect/vitest` (**must first fix the latent-broken backend-ts gate** — drop `--passWithNoTests`, make `it.effect` suites collect, de-duplicate the divergent `test/Modules/**` vs `test/unit/**` trees); `pytest` (Python until retired); the **visual verification harness** (Story 11 / spec 002) as the rendering gate; `paw verify`; `sentrux`/import-boundary checks (now enforced as package boundaries).

**Target Platform**: Backend service (`:8000` Python → `:8001` Effect), web app, Telegram/Google Chat channels, `paw` CLI, mobile.

**Deployment & clients**: backend on the **VPS** (one Cloudflared hostname). The **website** stays same-origin (cookie auth). **Desktop = Electron** (decided): ships the *same* Next.js frontend, **spawns the Next standalone server on loopback + `loadURL`s it** (real http origin — `next.config.ts` is already `output: 'standalone'`), and **proxies `/api/*` through the main process** with a **bearer token** (`safeStorage`) to a **runtime-configured** base URL (Settings screen + `electron-store`). Backend adds `HttpApiSecurity.bearer()` alongside the cookie so the same `/api/v1` endpoints serve web (cookie) and apps (bearer). **Mobile = Expo** (bearer). electron-builder + electron-updater + in-app update prompt. See [research.md](./research.md) §8.

**Project Type**: Full-stack monorepo — **tiny kernel + ~3 packages (kernel · `api-core` · host) + discovered capabilities + decoupled client apps** (web/mobile/CLI consume a generated typed client only).

**API surface**: one contract (`api-core`) → **HTTP** (`HttpApi`, auto-OpenAPI via `OpenApi.fromApi(Api)` + Scalar docs) **and Effect RPC** (`@effect/rpc`), both from the same `Domain`. A **typed client** is generated (`@hey-api/openapi-ts` → the read-only `api-client` package) — the single coupling for all clients. **Decomposition**: a thin core (`@platform/*` + `kernel` + `api-core`) + small uniform **`@clients/*`** packages (one per external SDK) + product sub-domain packages; comcom file conventions (`Domain·Api·Errors·RpcProtocol` contract / `Service·Repo·Policy·Http·Rpc` host; **no `index.ts` barrels**, `exports: "./*"`, `catalog:`/`workspace:*`).

**Performance Goals**: Domain-appropriate, small-now scale (first visible stream token < ~2s, per spec SC-001). Not designed for high-concurrency public multi-tenancy yet.

**Constraints**: **Default fully self-hosted** (Clarification Q1) — self-hosted Infisical, own-infra sandboxes, **no external AI gateway**. **Trusted users only** (Q2) — agent/model-generated *code* still sandbox-isolated (gVisor default). **Total migration** (Q3) — no Python in the end-state.

**Scale/Scope**: A handful of trusted self-hosted users; 16 stories; ~20 Python route groups to migrate; current backend is ~80% already the target shape (manifest plugin platform, AILLM Protocol, channel-agnostic runner).

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1.*

| Principle | Status | Notes |
|---|---|---|
| I. Evidence Before Claims | **PASS** | Every decision here is grounded in cited code (research.md): the strangler, the parts vocabularies, the substrate facts. Unknowns are listed, not guessed. |
| II. Preserve Architecture Boundaries | **PASS (reinforced)** | The plan's core thesis *is* boundary enforcement — promoting the advisory `no-tools-in-providers` / extension-boundaries / sentrux rules into **build-enforced package boundaries**. Optional integrations stay outside the kernel by construction. |
| III. Design System Consistency | **N/A here** | This program plan is backend/architecture; UI-touching stories (12, 15) defer DESIGN.md alignment to their own split specs. |
| IV. Gates Travel With the Change | **PASS (with a flagged defect)** | Each split slice names its gate (typecheck, `@effect/vitest`, harness compare, `paw verify`, sentrux). **The latent-broken backend-ts test gate is a defect this plan owns as Roadmap Step 0** — not deferred as "pre-existing." |
| V. Reviewable, Incremental Delivery | **PASS (via decomposition)** | See Complexity Tracking. The umbrella plan locks shared contracts only; each story splits into its own spec→plan→tasks→implement, each independently reviewable. No mega-implementation. |

**Result:** PASS. The only violation (one plan spanning 16 stories) is justified in Complexity Tracking and neutralized by per-split decomposition.

## Project Structure

### Documentation (this feature)

```text
specs/003-pawrrtal-overhaul/
├── plan.md              # this file
├── research.md          # Phase 0 — consolidated cross-cutting decisions
├── data-model.md        # Phase 1 — shared entities
├── quickstart.md        # Phase 1 — how to validate the program incrementally
├── contracts/           # Phase 1 — the 4 shared contracts every split inherits
│   ├── message-parts.md
│   ├── provider-taxonomy.md
│   ├── session-record.md
│   └── gateway.md
└── (per-split specs created later: specs/00N-<slice>/…)
```

### Source Code (target — thin core + small uniform packages in clean namespaces + decoupled clients)

> **Reconciling the references.** nanoclaw is ~2 packages; comcom is ~125; both are "elegant." Resolution: **"thin" is about the *core*, not the package count.** Keep the **foundation + the loop** tiny and zero-dependency (nanoclaw/Eve), then grow by adding **many small, single-responsibility packages in strict namespace layers** (comcom) so the dependency DAG reads off the namespace prefix. Pawrrtal adopts comcom's *layering + conventions + the 3-way capability rule*, but **starts with few packages** and adds one small package at a time. `backend-ts` already has the seam (`api-core` + `apps/api`). See [research.md](./research.md) §7.

```text
# THIN CORE (stays tiny + stable — the part that must be "really really thin")
@platform/*        effect · config · database · models · server · auth   — zero internal deps; shared by all runtimes
@pawrrtal/kernel   the agent-harness: ONE legible turn loop (build context → call provider → dispatch tools →
                   emit parts → park/continue/terminate) + a compaction policy + the 3 narrow ports
                   (provider · tool · channel). Imports nothing concrete.   (comcom names this @comcom/agent-harness)
@pawrrtal/api-core the CONTRACT — per-module Domain.ts · Api.ts (HttpApi) · Errors.ts (httpApiStatus) · RpcProtocol.ts.
                   Runtime-free. ⇒ auto-OpenAPI + auto typed-client + Effect RPC, all from these types.   [EXISTS]
@pawrrtal/api-client  GENERATED typed client (openapi.json → @hey-api/openapi-ts, or HttpApiClient). Never hand-edited.

# SMALL UNIFORM PACKAGES (grow one at a time; each single-responsibility; strict DAG by namespace)
@clients/*         one tiny Effect wrapper per external SDK/service — Client · Config · Errors, depends only on
                   @platform/effect:  anthropic · gemini · xai · codex · opencode · e2b · infisical · fireflies ·
                   mcp · ai-sdk · …   ← providers + integrations live HERE (not "plugins", not in the kernel)
@pawrrtal/*        product sub-domains, one responsibility each: app-core (frontend business logic) · app-shared (UI) ·
                   sandbox · secrets · sync · transcription · …   (comcom: @comcom/{app-core,sandbox,sync,…})

# RUNTIMES + CLIENTS (apps compose packages)
apps/api           HOST: server/ module impls (Service · Repo · Policy · Http · Rpc), discover→registry, serve
                   /openapi.json + Scalar /docs, persistence + auth + sessions + delivery at the EDGE.   [EXISTS, :8001]
apps/worker        background/scheduled runtime (optional; same contract).
apps/web           Next.js  — imports @pawrrtal/api-client + app-core only. NO backend imports.
apps/mobile        Expo     — same contract, generated client.
apps/paw           operator CLI (effect/unstable/cli) — HTTP client of the contract.

# CAPABILITIES — by the comcom 3-way rule (who owns/changes it decides where it lives):
#   user-added, runtime   → DB rows (skills, agents, user tools), injected into context at runtime
#   team-curated catalog  → declarative registry DATA in api-core (provider catalog · MCP catalog · integration apps) — metadata, no code
#   core business         → an in-trunk code module (the turn loop, conversations, projects)
#   external SDK          → a @clients/<service> package
```

**One contract, two transports:** each module's `Domain.ts` feeds **`Api.ts` (HttpApi → public REST + auto-OpenAPI, for web/mobile/external + the OpenAI/Anthropic gateway façade)** *and* **`RpcProtocol.ts` (Effect RPC → typed internal calls, e.g. the kernel↔host agent stream)** — both derived from the same types.

**File conventions (comcom):** contract module = `Domain.ts · Api.ts · Errors.ts · RpcProtocol.ts · [Events.ts]`; host module = `Service.ts · Repo.ts · Policy.ts · Http.ts · Rpc.ts`. PascalCase folders/files; complex domains nest (`Integrations/Domain/Substrate/`, `Catalog/`). **No `index.ts` barrels** — `exports: { "./*": "./src/*.ts" }`, callers import `@pawrrtal/api-core/Modules/Sessions/Domain` directly. Shared dep versions via `catalog:`; internal deps via `workspace:*`. Tests in `test/` at package root.

**Auto-generated OpenAPI + typed client (first-class, exact pipeline):** `OpenApi.fromApi(Api)` → a committed `openapi.json` → `@hey-api/openapi-ts` → the **`@pawrrtal/api-client` package** (read-only, regenerated on API change) → `@pawrrtal/app-core` (hooks/business logic) → frontends. Errors' `httpApiStatus` → error responses; middleware `security` → schemes; `OpenApi.annotations` → summaries; Scalar docs at `/docs`. **No hand-written spec; never hand-edit the generated client.**

**Structure Decision**: Partition by **code vs. data**, layer by **namespace**, and keep the *core* thin — not the package count. The test for any candidate package: *does it change when you add an agent / provider / channel / tool?* If yes → it is a **`@clients/*` wrapper, a registry-data file, or a DB row** (per the 3-way rule), never the kernel. The thin core (`@platform/*` + `kernel` + `api-core`) stays tiny and stable; the system grows by adding small uniform packages + catalog data + DB rows. `projects/conversations/settings` are host role-folders; providers/integrations are `@clients/*`; the kernel imports nothing concrete (build-enforced). The subtraction stories (#17–19) are what *let* the core be this thin.

**Deployment & client connection (research §8) — decisions locked.** Backend on the **VPS** (Cloudflared hostname). The **website** stays same-origin (cookies, unchanged). **Desktop = Electron** (decided), shipping the **same Next.js frontend** as the website — *not* a fork: one renderer behind a single platform-detection facade (`frontend/lib/desktop.ts` ↔ `window.pawrrtal`, the same idea as craft-agents' `window.electronAPI` built from one `CHANNEL_MAP`); web and desktop mount the same tree.

- **Desktop loads a locally-spawned Next *standalone* server via `loadURL('http://127.0.0.1:<port>')`** — *not* remote-navigate (just a branded browser; couples to VPS uptime + Cloudflare Access blocks non-browser clients) and *not* `file://`/`app://`/`next export` (breaks App Router/RSC and `window.origin`). A real local http origin keeps SSR/routing/cookies behaving; only `/api/*` goes remote. `next.config.ts` is already `output: 'standalone'`.
- **API calls proxied through the Electron main process** (hermes-style `desktop:apiFetch` IPC): main injects the **bearer token** + the **runtime base URL**, so there's **no CORS** and the token never reaches the renderer. Backend adds **`HttpApiSecurity.bearer()` alongside** the existing cookie `session_token` so the *same* `/api/v1` endpoints accept cookie (web) **or** bearer (desktop/mobile/CLI). SSE/chat: proxy over an IPC channel **or** a renderer fetch-stream with per-route CORS (decide per route).
- **Token (decided):** stored with Electron **`safeStorage`** (gate on `isEncryptionAvailable()`; warn on Linux `basic_text` fallback); access+refresh, single-in-flight refresh-on-401 in the main proxy; login via system-browser/device-code.
- **Runtime config (decided):** a Settings screen + `electron-store`; one resolver `getApiBaseUrl()` — web `''` (same-origin; never reintroduce web backend-URL selection), desktop = persisted value. Modes **Cloud | Local | Custom**. **Optional local-backend mode:** spawn FastAPI, health-poll `GET /api/v1/health`, flip the base URL only when healthy. (craft-agents' **channel-level routing** — local-only OS ops vs remote-eligible workspace calls — is the finer model if one window must mix both.)
- **Mobile = Expo**, bearer-only (same token path).
- **Distribution:** electron-builder per-OS (mac dmg arm64+x64, win nsis, linux AppImage; `asar:true`) + **electron-updater** with an **in-app `update-downloaded` → AppDialog prompt → `quitAndInstall()`** (no silent install; capture window/session state before update); signed/notarized (CSC_*/APPLE_*); on the OctavianTocan-gated self-hosted runner, with the **macOS notarize leg as the one gated `macos-latest` exception**.
- **Reconcile first:** the stale `docs/superpowers/plans/2026-03-26-electron-desktop-app.md` (Vite + `file://` + cookie-domain hack + sidecar) is **superseded** by these decisions; create the missing `electron/` workspace (`main.ts` spawn+loadURL · `server.ts` · `preload.ts` · `ipc.ts`) — referenced by `next.config.ts`/`dev-ports.ts` but not on disk this session (confirm whether a branch has it first).

## Phase 0 — Outline & Research → [research.md](./research.md)

Six fronts, all grounded in existing code, consolidated as Decision/Rationale/Alternatives in `research.md`:

1. **Existing Effect strangler** — build on `backend-ts/`; extend the Projects slice pattern; next slices from `router_registry.py` `_ROUTER_FACTORIES`; **fix the falsely-green test gate**.
2. **Effect v4 style (`../use-agy`)** — mirror the *compiling code* (Context.Service, Schema.TaggedErrorClass, `Effect.fn` span naming, layer/testLayer/fakeLayer, module file set), not the stale v3-flavored docs; reconcile beta.74↔.85 against `vendor/effect-smol`.
3. **Thin-core decomposition** — *refined by #7 below*: a tiny kernel (one loop + 3 ports) + ~3 packages (kernel · `api-core` · host); capabilities are **discovered files/data, not packages**; partition by **code vs. data**; the kernel imports nothing concrete (build-enforced); mirror into `backend-ts` `@pawrrtal/*`.
4. **Shared contracts** — collapse the 4 current event vocabularies onto `parts[]`; ModelProvider/AgentProvider taxonomy + capability manifest; session record + single context-owner; gateway internal-parts + external OpenAI/Anthropic façade.
5. **Self-hosted substrates** — self-hosted Infisical (Docker Compose + Machine Identity Universal Auth + `infisical run`), two secret planes kept separate; Docker+gVisor default sandbox + Kata strict tier (not self-hosted E2B); no external gateway.
6. **Persistence + migration** — Effect SQL (not Drizzle); Postgres-prod/SQLite-dev driver swap; Alembic single schema owner; extraction order Projects → read-only CRUD → paw CLI → message-write → streaming chat last.
7. **Thin-core references (nanoclaw · Eve · effect-smol · comcom)** — "thin = thin *core*, not few packages": **namespace-layered** packages with a tiny `@platform/*` + `kernel` + `api-core`; providers/integrations as uniform **`@clients/*`** packages; the **3-way capability rule** (user→DB · team→registry data · core→code module); **one contract → HTTP + RPC + auto-OpenAPI + generated client**; fully **decoupled frontends**. Refines #3.

## Phase 1 — Design & Contracts

- **Shared entities** → [data-model.md](./data-model.md)
- **The 4 shared contracts** → [contracts/](./contracts/) (message-parts · provider-taxonomy · session-record · gateway) — these are the load-bearing artifacts every split spec conforms to.
- **Validation guide** → [quickstart.md](./quickstart.md)
- **Agent context**: the SpecKit-managed plan reference in the agent context file is refreshed via the optional `after_plan` hook (`/speckit-agent-context-update`) rather than hand-editing the curated `CLAUDE.md`.

**Constitution re-check (post-design):** PASS — the contracts and decomposition *strengthen* boundary preservation (II) and keep delivery decomposable (V); no new violations introduced.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| One plan spanning all 16 stories (vs one plan per feature) | The maintainer directed a single master spec; the **cross-cutting contracts** (parts model, taxonomy, session, gateway) and the **package decomposition + migration sequence** are shared by every story and must be decided *once* and *coherently*. | Planning each feature first would re-derive these same shared contracts N times and risk N divergent versions — the exact fragmentation the umbrella exists to avoid. The plan ships nothing; tasks/implementation remain per-split and independently reviewable. |
| Two backends coexisting (`:8000` Python + `:8001` Effect) during migration | A total migration of ~20 route groups + 32 Alembic migrations cannot be a safe big-bang. | A big-bang rewrite has no parity safety net; the strangler already exists and works. |

## Sequencing Roadmap (which split specs, in what order)

Foundations first (P1), grounded in the dependency graph + migration sequence. Each step becomes its own `/speckit-specify` → plan → tasks → implement.

- **Step 0 — Fix the backend-ts test gate** (defect; gates-travel principle). Make `@effect/vitest` suites collect, drop `--passWithNoTests`, de-duplicate the test trees. Unblocks TDD on every later slice.
- **Step 1 — Lock the shared contracts in `@pawrrtal/api-core`** (parts, taxonomy, session, gateway façade) as typed `HttpApi` + `RpcProtocol` groups — which **auto-generate the OpenAPI spec, the Effect RPC surface, and the typed client** (the only client coupling). Pure contract; no behavior change.
- **Step 2 — Secrets (Story 5 / Spec M)** + **Sandbox (Story 4 / Spec T)**: self-hosted Infisical injection; Docker+gVisor sandbox behind the `sandbox` port. Foundational, low-throwaway, self-hosted.
- **Step 3 — Gateway + provider taxonomy (Story 3 / Spec S)**: normalized parts gateway, capability manifest, bidirectional sessions; the CLI-harness seam. Then **Claude provider (Story 7 / spec 001)** and **catalog/reasoning cleanup (Story 8 / Spec B)** land on it.
- **Step 4 — Shed dead weight (Story 6)**: remove permissions/budget/telemetry/workspaces (keep logging). Best done before extracting those modules to packages.
- **Step 5 — paw CLI → Effect (Story 2 pilot)**: pure HTTP client of the contracts; validates them from the consumer side with zero kernel coupling.
- **Step 6 — Thin-core extraction (Story 1 / Epic K)**: physically split `backend/app/*` into the package tree; promote boundaries to build-enforced.
- **Step 7 — Capability migration (strangler slices)**: read-only CRUD (workspaces, conversation metadata) → message-write slices → **streaming chat/turn last** (highest risk; flip per-route only after harness + parity gates).
- **Step 8 — Surfaces & capabilities**: rich media + verbosity toggles (Story 12), BYO-bot + headless onboarding (Story 13), provider auth (Story 9), active recall (Story 10), transcription/OpenClaw/Mirage plugins (Story 14), operability/versioning (Story 16), mobile (Story 15) — each on the now-stable core + contracts.
- **Step 9 — Deployment & app clients (Electron, decided)**: reconcile/supersede the stale `2026-03-26` electron plan + create the `electron/` workspace (`main`/`server`/`preload`/`ipc`); desktop **spawns the Next standalone server on loopback + `loadURL`s it**; **proxy `/api/*` through Electron main** with a **bearer token** (`safeStorage`, access+refresh, refresh-on-401 in the proxy) to a **runtime-configured** base URL (Settings: Cloud | Local | Custom, `electron-store`); add **`HttpApiSecurity.bearer()`** alongside the cookie in `api-core` Auth (web keeps cookies; both accepted on the same endpoints); give the `api-client` the **base-URL + auth-injector** knobs; **mobile (Expo, Story 15)** on the same bearer path; **electron-updater + in-app `update-downloaded` → AppDialog prompt → `quitAndInstall()`** (state captured first), signed/notarized on the gated runner (macOS notarize = the one `macos-latest` exception).

## Done When

- [x] Phase 0 research consolidated (`research.md`)
- [x] Phase 1 design artifacts generated (`data-model.md`, `contracts/*`, `quickstart.md`)
- [x] Constitution Check passed pre- and post-design
- [ ] Agent context refreshed via the optional `after_plan` hook
- [ ] Per-split specs created and planned individually (out of scope for this umbrella plan)
