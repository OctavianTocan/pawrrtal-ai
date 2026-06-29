# Implementation Plan: Pawrrtal Platform Overhaul — Program / Architecture Plan

**Branch**: `003-pawrrtal-overhaul` | **Date**: 2026-06-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-pawrrtal-overhaul/spec.md`

> **Plan altitude.** `003` is an umbrella spec, so this is a **program / architecture plan**, not a single buildable implementation plan. It resolves the *cross-cutting* research (Phase 0) and locks the *shared design* every story inherits (Phase 1): the four shared contracts, the thin-core package decomposition, the self-hosted substrates, and the incremental migration sequence. **Per-feature task lists (`/speckit-tasks`) and implementation happen per split spec** — see Complexity Tracking and the Sequencing Roadmap. This keeps the constitution's reviewable-increments principle intact: this plan ships nothing; it makes the splits coherent.

> **Persistence/runtime substrate (2026-06-27, spike-validated).** The persistence + runtime model (the `Storage:` and `Constraints:` lines, Phase 0 item 6, and the Step 7 cutover) is the four-store split from the ADR `frontend/content/docs/handbook/decisions/2026-06-27-rivet-postgres-electric-hatchet-substrate.mdx`, **proven end-to-end by the `spikes/rivet-pi-electric` M1–M9 spike** (`rivetkit` 2.3.2 — past the RC the ADR called its top risk; both state and alarm durability now proven). Live session state lives in a **per-conversation Rivet actor** running **Pi unforked**; the **queryable record lives in Postgres** (the API is its sole writer); **Electric** syncs Postgres read-models to all devices behind an identity-scoped gatekeeper; **Hatchet** runs system-level durable work. The substrate-agnostic `SessionStore`/`EventStreamStore` **ports are unchanged** — only their realization is fixed (per-actor store + an API-written Postgres projection). An earlier files-first/no-database model was the rejected alternative (see the ADR for why audience growth + multi-device live sync + v1 search moved the decision).

## Summary

Converge Pawrrtal onto a **tiny Effect-TS kernel + a small set of packages (kernel · `api-core` contracts · host) + capabilities as discovered files/data**, fronted by **one normalized gateway** that drives any model or full agent CLI, with **sandboxed execution**, **self-hosted secrets**, and the **removal** of the permission/budget/telemetry/workspace systems — migrating off Python via the **existing `backend-ts/` strangler** (Python `:8000` canonical, Effect `:8001` coexisting behind stable HTTP contracts). The technical approach is **continuity, not greenfield**: `backend-ts/` already encodes the `api-core`(contract)/`apps/api`(runtime) split, the Service/Repo/Body/Live patterns, Effect SQL, and cookie auth — with exactly one of ~21 Python route groups (Projects) ported. This plan locks the contracts and the decomposition so each split spec extends that one proven slice instead of re-deciding the architecture.

## Technical Context

**Language/Version**: End-state **TypeScript on Effect v4 (effect-smol)**; today Python 3.13/FastAPI (strangler coexistence). Frontend Next.js 15/React 19; mobile React Native/Expo (Story 15). *Version reconciliation needed:* `backend-ts` pins `effect@4.0.0-beta.74`; `../use-agy` pins `beta.85` — diff vendored revisions before copying signatures. **This drift is elevated to a PUBLISH BLOCKER for the SDK:** the internal boundary still picks ONE pin now, but there is **no publish until a stable non-`unstable`/non-`beta` Effect pin** lands and the `beta.74`↔`beta.85` gap is resolved to a single `peerDependency` range at the publish gate.

**Primary Dependencies**: `effect` v4 unstable surfaces (`effect/unstable/httpapi`, `effect/unstable/http`, `effect/unstable/rpc` — client/server protocol layers), `@effect/platform-bun`, `@effect/platform-browser` (`BrowserSocket` for the WS RPC transport; `BrowserWorker`/`BrowserWorkerRunner` for the deferred local MessagePort path), `@effect/vitest`; the **Pi package set** (`@earendil-works/pi-agent-core` core loop · `pi-ai` model layer **replacing `@effect/ai`** · `pi-tui` + `pi-coding-agent` default TUI/session/tools — all MIT, wrapped in Effect v4, unforked; Pi ships no MCP so MCP is a Pi extension); Bun; Biome. Source-of-truth for every signature = `backend/vendor/effect-smol` submodule (never guess an API).

**Storage**: A **four-store substrate** (ADR 2026-06-27, spike-validated). **(1)** Live session state — the transcript + agent/turn/queue/per-session-cron state — lives in a **per-conversation Rivet actor** running **Pi unforked**, persisted to the actor's own on-disk store and streamed over its built-in WebSocket; the actor schedules its **own per-session wakes** (`c.schedule.after`), durable across cold restarts and caught up on rehydration. **(2)** The **cross-cutting queryable record** (conversation list/metadata, profiles, projects, automations, integrations, settings, search) lives in **Postgres**, with the **API as sole writer**. **(3)** **Electric** syncs the Postgres read-models to every device through an **identity-scoped gatekeeper** (server-forced per-owner `where` + table/column allowlist; identity from a trusted session authority, never a client header). **(4)** **Hatchet** runs system-level durable work in a separate `apps/worker`, reaching a conversation only by messaging its actor. **Single-writer-per-store** is the load-bearing invariant (actor owns its session; API owns Postgres; actor↔API over RPC; no split-brain). Search defaults to shallow conversation **metadata** (the proven projection shape); a message-text **digest** or **full mirror** is a per-slice write-cost call, not a substrate risk. The `SessionStore`/`EventStreamStore` ports are unchanged; the SDK's standalone reference impl stays a simple **local store** (a node-FS `FileStore`). Pinned: `rivetkit` 2.3.2 · `pi` 0.80.2 · `@electric-sql/client` 1.5.13 · `@hatchet-dev/typescript-sdk` 1.24.3 · `effect` 4.0.0-beta.74 · Postgres 17 · `electricsql/electric` 1.5.1. The Python→Effect migration carries a one-shot exporter from the legacy SQLAlchemy tables into Postgres (not a file tree).

**Testing**: `@effect/vitest` (**must first fix the latent-broken backend-ts gate** — drop `--passWithNoTests`, make `it.effect` suites collect, de-duplicate the divergent `test/Modules/**` vs `test/unit/**` trees); `pytest` (Python until retired); the **visual verification harness** (Story 11 / spec 002) as the rendering gate; `paw verify`; `sentrux`/import-boundary checks (now enforced as package boundaries).

**Target Platform**: Backend service (`:8000` Python → `:8001` Effect), web app, Telegram/Google Chat channels, `paw` CLI, mobile.

**Deployment & clients**: backend on the **VPS**, exposed via **`tailscale serve`** (tailnet-only, never `funnel`; bound to `127.0.0.1`) — **Cloudflare Access is retired for app/API and the public website is deferred** (no brochure path now). **Identity = profiles + the spoof-proof `Tailscale-User-Login` header** that `serve` injects (trustworthy because the backend is loopback-bound and serve strips client copies); a profile MAY carry an **optional per-profile bearer** for password-locked profiles, held by the Electron main process and never exposed to the renderer. **Desktop = Electron** whose renderer uses **ONE Effect-RPC client over WebSocket** (`RpcClient.layerProtocolSocket` + `BrowserSocket.layerWebSocket(wss://<node>.ts.net/rpc)`) to the tailnet backend; the **MessagePort/local-runtime path** (`RpcClient.layerProtocolWorker` + `BrowserWorker.layer` to an Electron `utilityProcess`) is **DEFERRED post-v1**. The hardened `contextBridge` brokers the (deferred) MessagePort handshake + privileged native ops only — never the data path. **Mobile = Expo** over the same WS RPC. electron-builder + electron-updater + in-app update prompt. See [research.md](./research.md) §§9–11 (§8 superseded).

**Project Type**: Full-stack monorepo — **tiny kernel + ~3 packages (kernel · `api-core` · host) + discovered capabilities + decoupled client apps** (web/mobile/CLI consume a generated typed client only). The **kernel is the (internally-published) SDK** consumed by `apps/api` + `apps/paw` through the contract; the app→SDK arrow is build-enforced (see Structure Decision).

**API surface**: one contract (`api-core`) → **HTTP** (`HttpApi`, auto-OpenAPI via `OpenApi.fromApi(Api)` + Scalar docs) **and Effect RPC** (RpcGroups beside the HttpApi groups), both from the same `Domain`. **The Effect-RPC surface IS the desktop/web/mobile client transport** — reached via `RpcClient` over `RpcClient.layerProtocolSocket` (WebSocket for v1; the MessagePort local-runtime layer is deferred per Deployment), with **`AtomRpc.Service` as the reactive renderer binding**. A **typed client** is also generated (`@hey-api/openapi-ts` → the read-only `api-client` package) for HTTP consumers. **Decomposition**: a thin core (`@platform/*` + `kernel` + `api-core`) + small uniform **`@clients/*`** packages (one per external SDK) + product sub-domain packages; comcom file conventions (`Domain·Api·Errors·RpcProtocol` contract / `Service·Repo·Policy·Http·Rpc` host; **no `index.ts` barrels**, `exports: "./*"`, `catalog:`/`workspace:*`).

**Performance Goals**: Domain-appropriate, small-now scale (first visible stream token < ~2s, per spec SC-001). Not designed for high-concurrency public multi-tenancy yet.

**Constraints**: **Default fully self-hosted** (Clarification Q1) — self-hosted Infisical, own-infra sandboxes, **no external AI gateway**. **Substrate persistence (ADR 2026-06-27, spike-validated)** — per-conversation Rivet actors (live session state) + Postgres (API-written queryable record) + Electric (read-path sync) + Hatchet (system-level durable work); still fully self-hostable, but the "self-hosted by default" promise now means running a Rivet engine, Postgres, an Electric sync service, and a Hatchet engine (Hatchet + Electric reuse the same Postgres server; each ships as a single binary/container — see research §13). **Trusted users only** (Q2) — agent/model-generated *code* still sandbox-isolated (**`local-confined` default; Docker+gVisor/Kata/E2B opt-in tiers**), independent of the actor's session isolation. **Total migration** (Q3) — no Python in the end-state.

**Scale/Scope**: A handful of trusted self-hosted users; 16 stories; ~20 Python route groups to migrate; current backend is ~80% already the target shape (manifest plugin platform, AILLM Protocol, channel-agnostic runner).

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1.*

| Principle | Status | Notes |
|---|---|---|
| I. Evidence Before Claims | **PASS** | Every decision here is grounded in cited code (research.md): the strangler, the parts vocabularies, the substrate facts. Unknowns are listed, not guessed. |
| II. Preserve Architecture Boundaries | **PASS (reinforced)** | The plan's core thesis *is* boundary enforcement — promoting the advisory `no-tools-in-providers` / extension-boundaries / sentrux rules into **build-enforced package boundaries**. Optional integrations stay outside the kernel by construction. |
| III. Design System Consistency | **N/A here** | This program plan is backend/architecture; UI-touching stories (12, 15) defer DESIGN.md alignment to their own split specs. |
| IV. Gates Travel With the Change | **PASS (with a flagged defect)** | Each split slice names its gate (typecheck, `@effect/vitest`, harness compare, `paw verify`, sentrux). **The latent-broken backend-ts test gate is a defect this plan owns as Roadmap Step 0** — not deferred as "pre-existing." |
| V. Reviewable, Incremental Delivery | **PASS (via stacked PRs)** | See Complexity Tracking. The umbrella plan locks shared contracts only; the **maintainer-agent implements every slice as small, parallel-stacked PRs, each independently gated** (typecheck, `@effect/vitest`, harness, `paw verify`, sentrux). The per-split-spec decomposition is a **sequencing device, not an ownership boundary**. No mega-implementation. |

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
# ── PUBLISHABLE UNIT (internal in v1): kernel + api-core + @clients/* + the `paw` AGENT group.
#    This IS the publishable-shaped SDK boundary; we name it publishable-shaped and BUILD-ENFORCE the
#    app→SDK dependency arrow now, but ship nothing public yet (publish DEFERRED, NOT CHOSEN — see Step 6
#    + the publish blocker in Technical Context). The SDK imports NO app/runtime/host code: the arrow points
#    apps/api + apps/paw → SDK, never back. Keep the `pawrrtal`/`@pawrrtal/*` scope internally; an
#    `agentkit` scope is aliased ONLY at publish-time, never squatted now.
@platform/*        effect · config · database · models · server · auth   — zero internal deps; shared by all runtimes.
                   Lives at packages/platform.   [NEW — only api-core + apps/api exist today]
@pawrrtal/kernel   the agent-harness / SDK CORE — sits ABOVE api-core in the publishable unit: wraps Pi's agentLoop (in Effect)
                   (build context → call provider → dispatch tools → emit parts → park/continue/terminate) + a
                   compaction policy + the narrow ports as interfaces only (provider · tool+permission-check · channel ·
                   sandbox · file/session store · secret · memory · observability). Imports nothing concrete; ships
                   trivial reference impls only (LocalConfinedRuntime · node-FS FileStore · dev provider stub).
                   Lives at packages/kernel.   [NEW]   (comcom names this @comcom/agent-harness)
@pawrrtal/api-core the CONTRACT — per-module Domain.ts · Api.ts (HttpApi) · Errors.ts (httpApiStatus) · RpcProtocol.ts.
                   Runtime-free. ⇒ auto-OpenAPI + auto typed-client + Effect RPC, all from these types.   [EXISTS]
@pawrrtal/api-client  GENERATED typed client (openapi.json → @hey-api/openapi-ts, or HttpApiClient). Never hand-edited.
                   Lives at packages/api-client.   [NEW]

# SMALL UNIFORM PACKAGES (grow one at a time; each single-responsibility; strict DAG by namespace)
@clients/*         one tiny Effect wrapper per external SDK/service — Client · Config · Errors, depends only on
                   @platform/effect:  anthropic · gemini · xai · codex · opencode · e2b · infisical · fireflies ·
                   mcp · ai-sdk · acp · …   ← providers + integrations live HERE (not "plugins", not in the kernel).
                   ALL live under packages/clients/* (a curated STARTER SUBSET ships only at publish-time).
                   Part of the publishable unit.   [NEW — glob packages/clients/*]
@pawrrtal/*        product sub-domains, one responsibility each: app-core (frontend business logic) · app-shared (UI) ·
                   sandbox · secrets · sync · transcription · …   (comcom: @comcom/{app-core,sandbox,sync,…})

# RUNTIMES + CLIENTS (apps compose packages — these depend ON the SDK; the arrow never points back)
apps/api           HOST: server/ module impls (Service · Repo · Policy · Http · Rpc), discover→registry, serve
                   /openapi.json + Scalar /docs, persistence + auth + sessions + delivery at the EDGE.   [EXISTS, :8001]
apps/worker        background/scheduled runtime (optional; same contract).
apps/web           Next.js  — imports @pawrrtal/api-client + app-core only. NO backend imports.   [NEW]
apps/mobile        Expo     — same contract, generated client.   [NEW]
apps/paw           ONE `paw` binary, two groups — do NOT split: the AGENT group (new · dev --no-ui · run --payload ·
                   build · info) is KERNEL-ONLY by construction and is part of the publishable unit (aliased as an
                   `agentkit` bin at publish); the OPERATOR group (verify · lab · live-ops · profiles) is a Pawrrtal
                   HTTP/RPC client of the contract and stays in the app. Today Python at backend/app/cli/paw.   [NEW]

# CAPABILITIES — by the comcom 3-way rule (who owns/changes it decides where it lives):
#   user-added, runtime   → DB rows (skills, agents, user tools), injected into context at runtime
#   team-curated catalog  → declarative registry DATA in api-core (provider catalog · MCP catalog · integration apps) — metadata, no code
#   core business         → an in-trunk code module (the turn loop, conversations, projects)
#   external SDK          → a @clients/<service> package
```

**One contract, two transports:** each module's `Domain.ts` feeds **`Api.ts` (HttpApi → public REST + auto-OpenAPI, for web/mobile/external + the OpenAI/Anthropic gateway façade)** *and* **`RpcProtocol.ts` (Effect RPC → typed internal calls, e.g. the kernel↔host agent stream)** — both derived from the same types.

**File conventions (comcom):** contract module = `Domain.ts · Api.ts · Errors.ts · RpcProtocol.ts · [Events.ts]`; host module = `Service.ts · Repo.ts · Policy.ts · Http.ts · Rpc.ts`. PascalCase folders/files; complex domains nest (`Integrations/Domain/Substrate/`, `Catalog/`). **No `index.ts` barrels** — `exports: { "./*": "./src/*.ts" }`, callers import `@pawrrtal/api-core/Modules/Sessions/Domain` directly. Shared dep versions via `catalog:`; internal deps via `workspace:*`. Tests in `test/` at package root.

**Auto-generated OpenAPI + typed client (first-class, exact pipeline):** `OpenApi.fromApi(Api)` → a committed `openapi.json` → `@hey-api/openapi-ts` → the **`@pawrrtal/api-client` package** (read-only, regenerated on API change) → `@pawrrtal/app-core` (hooks/business logic) → frontends. Errors' `httpApiStatus` → error responses; middleware `security` → schemes; `OpenApi.annotations` → summaries; Scalar docs at `/docs`. **No hand-written spec; never hand-edit the generated client.**

**Structure Decision**: Partition by **code vs. data**, layer by **namespace**, and keep the *core* thin — not the package count. The test for any candidate package: *does it change when you add an agent / provider / channel / tool?* If yes → it is a **`@clients/*` wrapper, a registry-data file, or a DB row** (per the 3-way rule), never the kernel. If it is *this-tailnet / this-profile / this-substrate (Rivet actor + Postgres + Electric)*-specific → it is the **app**, not the SDK. The thin core (`@platform/*` + `kernel` + `api-core`) stays tiny and stable; the system grows by adding small uniform packages + catalog data + DB rows. `projects/conversations/settings` are host role-folders; providers/integrations are `@clients/*`; the kernel imports nothing concrete except the Pi harness it wraps (build-enforced). The subtraction stories (#17–19) are what *let* the core be this thin.

**The publishable SDK boundary is build-enforced now (publish itself is DEFERRED, NOT CHOSEN).** The **publishable unit** = `kernel` + `api-core` + `@clients/*` + the `paw` AGENT group; we name it publishable-shaped and enforce the **app→SDK dependency arrow** (`apps/api` + `apps/paw` → SDK) so the SDK imports **no app/runtime/host code** — but we ship nothing public in v1. Publishing waits on four gates: (1) the four shared contracts API-frozen for 2+ cycles, (2) a stable non-`unstable`/non-`beta` Effect pin (the publish blocker in Technical Context), (3) 2+ in-repo consumers through the generated contract, (4) an external party asking. The GATEWAY is the only split entity — the internal parts envelope is SDK, the external OpenAI/Anthropic façade is app. **First mechanical step:** widen `backend-ts/package.json` workspaces to include `packages/clients/*` and add `kernel` + `platform` (workspace-protocol deps, `catalog:` versions, no `index.ts` barrels).

**Deployment & client connection (research §§9–11) — decisions locked.** The earlier **Next-standalone-`loadURL` + `desktop:apiFetch` HTTP-proxy + `safeStorage`-bearer + per-route-CORS + Cloud|Local|Custom base-URL machinery is SUPERSEDED.** The new locked decisions:

- **`tailscale serve` (tailnet-only) replaces Cloudflare Access for the app/API** — the backend is bound to `127.0.0.1` and exposed only over the tailnet (never `funnel`); **a public website is deferred, not chosen**. No CORS / cookie-domain concerns (the renderer rides WSS RPC, not cross-origin HTTP).
- **Profiles replace cookie/bearer login.** Identity = a `Tailscale-User-Login` header (spoof-proof: loopback-bound backend, `serve` strips client copies) + an `X-Pawrrtal-Profile: <id>` header on every request. A profile MAY carry an **optional password**; unlocking it returns a short-lived **opaque bearer used only for password-locked profiles**, held by the **Electron main process and never exposed to the renderer**.
- **The renderer reaches the backend through ONE Effect-RPC contract over WebSocket (v1)** — `RpcClient.layerProtocolSocket` + `BrowserSocket.layerWebSocket(wss://<node>.ts.net/rpc)`, with streaming as Effect `Stream` returns (ack-based backpressure + interrupt cancellation), **not** `ipcMain.invoke`/`webContents.send`. The **MessagePort local-runtime transport** (`RpcClient.layerProtocolWorker` + `BrowserWorker.layer` to an Electron `utilityProcess`) is **DEFERRED post-v1** as the future local-first option.
- **`contextBridge` / `sandbox` stay the security floor** (`contextIsolation:true, sandbox:true, nodeIntegration:false`, validated `event.senderFrame`, never exposes `ipcRenderer`) — the handshake that brokers the one-time (deferred) MessagePort handoff + privileged native ops, **never the data path**.
- **Mobile = Expo** over the same WS RPC.
- **Distribution unchanged:** electron-builder per-OS (mac dmg arm64+x64, win nsis, linux AppImage; `asar:true`) + **electron-updater** with an **in-app `update-downloaded` → AppDialog prompt → `quitAndInstall()`** (no silent install; capture window/session state before update); signed/notarized (CSC_*/APPLE_*); on the OctavianTocan-gated self-hosted runner, with the **macOS notarize leg as the one gated `macos-latest` exception**.
- **Reconcile first:** the stale `docs/superpowers/plans/2026-03-26-electron-desktop-app.md` (Vite + `file://` + cookie-domain hack + sidecar) is **superseded**; create the greenfield `electron/` workspace (main window · preload validated `window.pawrrtal` handshake · the runtime entry for the DEFERRED local path) — referenced by `next.config.ts`/`dev-ports.ts` but not on disk this session (confirm whether a branch has it first).

## Phase 0 — Outline & Research → [research.md](./research.md)

Six fronts, all grounded in existing code, consolidated as Decision/Rationale/Alternatives in `research.md`:

1. **Existing Effect strangler** — build on `backend-ts/`; extend the Projects slice pattern; next slices from `router_registry.py` `_ROUTER_FACTORIES`; **fix the falsely-green test gate**.
2. **Effect v4 style (`../use-agy`)** — mirror the *compiling code* (Context.Service, Schema.TaggedErrorClass, `Effect.fn` span naming, layer/testLayer/fakeLayer, module file set), not the stale v3-flavored docs; reconcile beta.74↔.85 against `vendor/effect-smol`.
3. **Thin-core decomposition** — *refined by #7 below*: a tiny kernel (one loop + 3 ports) + ~3 packages (kernel · `api-core` · host); capabilities are **discovered files/data, not packages**; partition by **code vs. data**; the kernel imports nothing concrete (build-enforced); mirror into `backend-ts` `@pawrrtal/*`.
4. **Shared contracts** — collapse the 4 current event vocabularies onto `parts[]`; ModelProvider/AgentProvider taxonomy + capability manifest; session record + single context-owner; gateway internal-parts + external OpenAI/Anthropic façade.
5. **Self-hosted substrates** — self-hosted Infisical (Docker Compose + Machine Identity Universal Auth + `infisical run`), two secret planes kept separate; **`local-confined` default sandbox** (constrained CWD + network-off via OS primitives like bubblewrap, no container/image); **Docker+gVisor / Kata / E2B opt-in tiers; Upstash Box opt-in only** (managed-cloud, conflicts with self-hosted); no external gateway.
6. **Persistence + migration** — the **four-store substrate** (ADR 2026-06-27, spike-validated): per-conversation Rivet actors (live session state, Pi unforked) + Postgres (API-written queryable record) + Electric (identity-scoped read-path sync) + Hatchet (system-level durable work); **single-writer-per-store** is the invariant; extraction order Projects → read-only CRUD → paw CLI → message-write → streaming chat last.
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
| One plan spanning all 16 stories (vs one plan per feature) | The maintainer directed a single master spec; the **cross-cutting contracts** (parts model, taxonomy, session, gateway) and the **package decomposition + migration sequence** are shared by every story and must be decided *once* and *coherently*. | Planning each feature first would re-derive these same shared contracts N times and risk N divergent versions — the exact fragmentation the umbrella exists to avoid. The plan ships nothing; the **maintainer-agent implements every slice as small, parallel-stacked PRs, each independently gated** — the per-split-spec decomposition is a **sequencing device, not an ownership boundary** (there are no separate per-feature owners). |
| Two backends coexisting (`:8000` Python + `:8001` Effect) during migration | A total migration of ~20 route groups + 32 Alembic migrations cannot be a safe big-bang. | A big-bang rewrite has no parity safety net; the strangler already exists and works. |

## Sequencing Roadmap (which split specs, in what order)

Foundations first (P1), grounded in the dependency graph + migration sequence. Each step becomes its own `/speckit-specify` → plan → tasks → implement.

- **Step 0 — Fix the backend-ts test gate** (defect; gates-travel principle). Make `@effect/vitest` suites collect, drop `--passWithNoTests`, de-duplicate the test trees. Unblocks TDD on every later slice.
- **Step 1 — Lock the shared contracts in `@pawrrtal/api-core`** (parts, taxonomy, session, gateway façade) as typed `HttpApi` + `RpcProtocol` groups — which **auto-generate the OpenAPI spec, the Effect RPC surface, and the typed client** (the only client coupling). Pure contract; no behavior change.
- **Step 2 — Secrets (Story 5 / Spec M)** + **Sandbox (Story 4 / Spec T)**: self-hosted Infisical injection; the **default `local-confined` driver** (constrained CWD + network-off, no container) behind the `sandbox:runtime` slot, with **Docker+gVisor / Kata / E2B / `gondolin-microvm` (self-hosted Alpine micro-VM) / Upstash Box as opt-in tier plugins** (`default:false` manifests); the port's `pause`/`resume` is **provider-agnostic and best-effort** (live memory+FS snapshot where supported, else disk-checkpoint + cold resume), so any provider fits. Foundational, low-throwaway, self-hosted. The core MUST NOT import a sandbox runtime — only the `SandboxRuntime` port + the tiny `LocalConfinedRuntime` reference impl live near core. (`gondolin` + `pi-chat` are **reference implementations**, not deps.)
- **Step 3 — Gateway + provider taxonomy (Story 3 / Spec S)**: normalized parts gateway, capability manifest, bidirectional sessions; the CLI-harness seam. Add the **non-core `@clients/acp` package** (Client · Config · Errors · Schema · Registry; the official `@agentclientprotocol/sdk` wrapped in Effect — `@effect/platform` `Command` to spawn, `Stream` for session/update, `Scope`/`acquireRelease` for subprocess lifecycle, tagged Errors; no `index.ts` barrel, `exports: "./*"`) **+ one host-side AgentProvider adapter under `apps/api/src/Modules/`** — the **successor** to the hand-rolled `agy_cli`/`claude_code_pty` bridges, not a fourth one. Targets: **Gemini CLI (native ACP) first, then Claude Code (`@zed-industries/claude-code-acp`), then Codex (`codex-acp`)**. It declares **`tool_enforcement: enforced`** (the host implements ACP's `session/request_permission` + `fs/*` + `terminal/*` callbacks against Pawrrtal's own workspace/sandbox); `session/update` variants map onto the unified `parts[]` vocabulary; the ACP `sessionId` is the provider-session handle; **known agents = Registry data rows**. **Widen the backend-ts workspaces glob to `packages/clients/*`, and stand up the two empty SDK-foundation packages — `packages/platform` (zero internal deps) and `packages/kernel` (the one-loop core + ports as interfaces; imports nothing concrete)** — so the publishable unit (`kernel` + `api-core` + `@clients/*` + the `paw` agent group) has a home before the loop is extracted into it (Step 6). Then **Claude provider (Story 7 / spec 001)** and **catalog/reasoning cleanup (Story 8 / Spec B)** land on it.
- **Step 4 — Shed dead weight (Story 6)**: remove permissions/budget/telemetry/workspaces (keep logging). Best done before extracting those modules to packages. Also **delete `backend/Dockerfile`** (the Python app image; the Effect API runs as a plain Bun process on the tailnet). The app-serving `docker-compose*.yml` files lose their *old* job (no containerized Python+app-Postgres), but a **substrate compose stack returns** for the infra the ADR requires — **Postgres** (shared by Electric + Hatchet as separate logical DBs), **Electric**, and **Hatchet** — alongside the **Rivet engine** (in-process in dev, a binary/container in prod). So Docker is no longer absent from a clean install; it (or equivalent single binaries) hosts the substrate. The Docker engine also still backs the **opt-in Infisical + docker-gvisor sandbox tiers**. See research §13.
- **Step 4.1 — Removal audit (required before Step 6):** enumerate every planned removal that is currently implicit and lock it into the plan as an explicit contract item, so no legacy subsystem is accidentally kept because it was never written down. The audit must include:
  - auth/session path replacements (cookie + dev-login + OAuth entry surfaces)
  - provider/runtime registration surfaces that should disappear with new profile-first auth
  - legacy workspace/permission/budget/telemetry assumptions in host and runtime slices
  - obsolete deployment paths and compose jobs
  - any non-core code owned solely by removed systems
  - one-line acceptance test for each removal (build, import, or runtime behavior proves removal is real)

  The output is a single “Removal Completeness Matrix” section added to this plan before any code deletes proceed.
- **Step 5 — paw CLI → Effect (Story 2 pilot), as ONE binary with TWO groups**: the **OPERATOR group** (`verify · lab · live-ops · profiles`) is a pure HTTP/RPC client of the contracts — validates them from the consumer side with zero kernel coupling; the **AGENT group** (`new · dev --no-ui · run --payload · build · info`) is **kernel-only by construction** and is the **dogfood-by-extraction consumer that PROVES the SDK boundary** (it imports the publishable unit and nothing app-side; `run --payload` is the CI primitive + non-HTTP dispatch entry on the same kernel). Do NOT split the binary; alias the agent group as an `agentkit` bin only at publish. This is the first in-repo consumer of the SDK arrow.
- **Step 6 — Thin-core extraction (Story 1 / Epic K)**: physically split `backend/app/*` into the package tree; promote boundaries to build-enforced. **This step crystallizes the PUBLISHABLE BOUNDARY** — **Pi's `agentLoop` wrapped in Effect v4 (the core loop, unforked — not hand-rolled)** + compaction + ports land in `packages/kernel` (Pi is the one sanctioned kernel dependency), joining `api-core` + `@clients/*` + the `paw` agent group as the publishable unit, with the **app→SDK arrow build-enforced** (the SDK imports no app/runtime/host code). **In v1 this is internal only:** NO npm-publish pipeline, NO public `index.ts` barrel, NO independent version cadence — the unit is named publishable-shaped but ships nothing public until the four publish gates clear (contracts API-frozen 2+ cycles · stable Effect pin · 2+ in-repo consumers · an external ask). Publishing is **DEFERRED, NOT CHOSEN.**
- **Step 7 — Capability migration + substrate cutover (strangler slices)**: read-only CRUD (workspaces, conversation metadata) → message-write slices → **streaming chat/turn last** (highest risk; flip per-route only after harness + parity gates). The **persistence cutover** (ADR 2026-06-27, spike-validated) stands up the four stores and moves conversations onto them: stand up the **Postgres** schema (API as sole writer) + the **Rivet engine** host for per-conversation actors (Pi unforked) + the **Electric** identity-scoped gatekeeper + the **Hatchet** `apps/worker`; the streaming-chat slice is where a conversation's live state moves into its actor (transcript + turn state on the actor, synced to a Postgres projection the API writes and Electric pushes to devices). A **one-shot SQLAlchemy→Postgres importer** carries legacy conversations/profiles/projects/memory into the queryable record; per-conversation transcript history is replayed into each actor on first touch. **Build in the spike's operational sharp edges, don't rediscover them:** engine-port hygiene before boot (FINDINGS #11), settle/commit before a hard kill since actor state persists asynchronously (#12/#17), a pinned durable runner version (#5), the Hatchet token embedding its gRPC broadcast address (#15), and the Electric gatekeeper's allowlist-forwarding (not denylist) security model + forwarding the client disconnect to the upstream long-poll (#9/#10).
- **Step 8 — Surfaces & capabilities**: rich media + verbosity toggles (Story 12), BYO-bot + headless onboarding (Story 13), provider auth (Story 9), active recall (Story 10), transcription/OpenClaw/Mirage plugins (Story 14), operability/versioning (Story 16), mobile (Story 15) — each on the now-stable core + contracts.
- **Step 9 — Deployment & app clients (tailnet + RPC, decided)**: **expose the backend via `tailscale serve` on a tailnet node** (loopback-bound, never `funnel`), **retire Cloudflare Access for app/API**, **website deferred**. Add the **profiles slice**: backend `GET /profiles` + `POST /profiles/{id}/unlock`; api-core **`ProfileMiddlewareService` / `ProfileStore` replacing `SessionStore`**. Create the **greenfield `electron/` workspace** (main window + preload validated `window.pawrrtal` handshake + the runtime entry for the **DEFERRED local path**); the **renderer RPC client = WebSocket to the tailnet backend (v1)** via `RpcClient.layerProtocolSocket` + `BrowserSocket.layerWebSocket`; **mobile (Expo, Story 15)** on the same WS RPC; **electron-updater + in-app `update-downloaded` → AppDialog prompt → `quitAndInstall()`** (state captured first), signed/notarized on the gated runner (macOS notarize = the one `macos-latest` exception). **AUTH reconciliation note:** finish the in-flight cookie-session Effect strangler slice as a **learning exercise**, then land a **follow-up profiles slice reusing the same `HttpApiMiddleware` scaffolding** — swap `apiKey(cookie)`→`bearer`/none and `SessionStore`→`ProfileStore`.

## Done When

- [x] Phase 0 research consolidated (`research.md`)
- [x] Phase 1 design artifacts generated (`data-model.md`, `contracts/*`, `quickstart.md`)
- [x] Constitution Check passed pre- and post-design
- [ ] Agent context refreshed via the optional `after_plan` hook
- [ ] Per-split specs created and planned individually (out of scope for this umbrella plan)
