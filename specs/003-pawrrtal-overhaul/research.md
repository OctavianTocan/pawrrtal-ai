# Phase 0 Research — Pawrrtal Overhaul Program Plan

Consolidated cross-cutting decisions, grounded in existing code (six parallel research fronts). Format: Decision / Rationale / Alternatives. Citations are repo paths.

---

## 1. Build on the existing Effect strangler (`backend-ts/`), not greenfield

- **Decision**: Treat `backend-ts/` as the canonical target to extend. It is a real, working migration with **1 of ~21** Python route groups ported (Projects CRUD + System health + cookie auth), as `@pawrrtal/api-core` (contract: HttpApi groups, `Domain.ts`, `Errors.ts`) + `@pawrrtal/api` (runtime: `Http.ts`/`Service.ts`/`Repo.ts`/`Layers.ts`/`Infrastructure/`). Pins `effect@4.0.0-beta.74` against the `backend/vendor/effect-smol` submodule. Serves on `:8001` (default-on via `dev.ts`; `PAWRRTAL_SKIP_TS_API=1` opts out).
- **Rationale**: All scaffolding, conventions (`CONVENTIONS.md`), vendor pinning, dev-port wiring, and one fully-wired slice already typecheck. The next slices come from `backend/app/infrastructure/router_registry.py:12-33` `_ROUTER_FACTORIES`.
- **Alternatives**: Greenfield rewrite (rejected — discards working contract+runtime wiring); abandoning the strangler (rejected — Python is canonical only "until route parity").
- **The v4 module recipe to replicate per slice**: api-core `Domain.ts` (Schema.Class) + `Errors.ts` (`Schema.TaggedErrorClass` w/ `httpApiStatus`) + `Api.ts` (`HttpApiGroup.make('<id>')…middleware(Auth).prefix`); apps/api `Repo.ts` (Context.Service + Body/Live, `SqlClient`) + `Service.ts` + `Http.ts` (`HttpApiBuilder.group`, **swap `STUB_USER_ID` for `yield* CurrentUser`**) + add to `Modules/Layers.ts` `CoreModulesLive` + add table DDL.
- **Auth model during migration**: TS validates the same `session_token` cookie by calling Python `GET /api/v1/users/me` (`SessionStore`), so **Python stays the auth authority** — a migrated slice does not reimplement fastapi-users to be protected. (Handlers still use `STUB_USER_ID`; swapping to `CurrentUser` is the next concrete step.)
- **⚠ Defect to fix (Roadmap Step 0)**: the test gate `bun --bun vitest run --passWithNoTests` reports green but **0 `@effect/vitest` suites collect** (node vitest dies on `bun:sqlite`); ~1000 lines of real assertions never run. Plus a **duplicated, divergent** test tree (`apps/api/test/Modules/**` vs `apps/api/test/unit/**`). Treat as a real failure (no-pre-existing-excuse): fix collection, drop `--passWithNoTests`, de-duplicate. Cite: `backend-ts/{README.md,CONVENTIONS.md,package.json}`, `backend-ts/apps/api/src/Modules/Projects/*`, `backend/app/infrastructure/router_registry.py:12-33`.

## 2. Effect v4 style — mirror `../use-agy`'s code, not its docs

- **Decision**: Use `Context.Service<Self, Shape>()(id)` for services, `Schema.TaggedErrorClass` for errors (with `declare readonly cause: unknown` + constructor for JS causes), granular namespace imports (`import * as Effect from 'effect/Effect'`), `effect/unstable/*` submodules, `@effect/platform-bun` runtime, `Effect.fn('Service.method')` for traced methods, and a `layer`/`testLayer`/`fakeLayer` trio per module. Module file set: `Domain.ts`, `Service.ts`, `Errors.ts`, `Repo.ts`, `Api.ts`, `Http.ts`, `Policy.ts` (PascalCase, no `index.ts` barrels).
- **Rationale**: `../use-agy`'s compiling source (`packages/use-agy/effect/src/Modules/Agy/*`) uses the **real** beta.85 API and matches `vendor/effect-smol/migration/services.md`. **CRITICAL caveat**: `use-agy`'s `.agents/skills/domain-effect/**` *example docs* still teach v3-era API (`Effect.Service`, `Schema.TaggedError`, barrel imports, `@effect/platform`) — those are structural guidance only, not literal API. Always verify signatures against `vendor/effect-smol`.
- **Alternatives**: Following the example-doc API verbatim (rejected — stale v3). `Effect.Service.Default` auto-layer (v3) vs explicit `Layer.effect` + named `layer` (v4, what the real code ships).
- **Open**: **version drift** — `use-agy` pins beta.85, `backend-ts` beta.74; diff the two vendored effect-smol revisions before copying signatures; pick one target. `use-agy` has **no** running HttpApi/SQL exemplar (apps/api is a stub) — lean on `vendor/effect-smol/ai-docs` + the existing `backend-ts` Projects slice for live HttpApi+SQL wiring.

## 3. Thin-core + capability-package + plugin decomposition

- **Decision**: The **tiny core** = exactly five concerns: (1) turn-pipeline orchestration, (2) the streamed-parts contract, (3) the provider-neutral model/tool loop, (4) the extension Protocols as pure interfaces (provider/channel/tool/context/memory/secrets/sandbox), (5) the plugin loader. Every capability becomes a **top-level package** owning its contract + slot + tests; every concrete impl (each provider, each channel, OpenClaw, Mirage, each STT/sandbox backend) is a **plugin** behind a slot. The core's forbidden deps are a **build-enforced deny-list**.
- **Rationale**: The current backend is ~80% this shape already — manifest plugin platform (`app/plugins/{registry,host,discovery,contributions}.py` with a full capability-type Literal taxonomy), `AILLM` Protocol as the only provider surface the runner knows (`runner.py:238`), tool composition hoisted to `tool_surface.py`, channel-agnostic `Channel.receive/deliver`. Promoting the advisory `no-tools-in-providers`/extension-boundaries/sentrux rules to **physical package boundaries** makes the build fail instead of a lint warning (sentrux already *couldn't* pin `app.tools`/`app.lcm`/`app.turns` to a layer — physical packages force the split).
- **Alternatives**: Import-linter contracts only (rejected — advisory, documented gaps); two-package core+everything (rejected — defeats swappability; the transcription removal proved optional subsystems must be physically removable).
- Full **current→target module map** in the workflow output; mirror packages into `backend-ts` as `@pawrrtal/*`. Cite: `app/providers/base.py:104`, `app/plugins/contributions.py:177`, `app/channels/base.py`, `.sentrux/rules.toml`, `.claude/rules/architecture/no-tools-in-providers.md`.
- **The tiny core IS the publishable SDK boundary** — see ## 16 Kernel-as-SDK, which names the five concerns above as the SDK-owned unit and build-enforces the app→SDK dependency arrow now (publish deferred).

## 4. The four shared contracts (collapse 4 event vocabularies → `parts[]`)

- **Decision**: Adopt the four contracts in [contracts/](./contracts/): **message-parts** (`parts: Part[]` ordered/complete/lossless = the message; StreamEvent becomes a delta-transport), **provider/harness taxonomy** (ModelProvider vs AgentProvider + a declared CapabilityManifest), **session record** (bidirectional mapping + exactly one `context_owner`), **gateway** (internal parts + external OpenAI/Anthropic façade reusing the channel `deliver` seam).
- **Rationale**: Today four overlapping shapes exist — `LLMEvent` (`types.py:101`), `AgentEvent` (`types.py:171`), `StreamEvent` (`base.py:25`), and the **lossy persisted `timeline`** (`frontend/lib/types.ts:58` — only holds `thinking`/`tool`, so true text↔tool interleave order is lost). The `agent_event_to_stream_event` seam (`events.py:19`) maps only 5 of N types and silently drops the rest. One complete `parts[]` removes the hand-maintained live-vs-rehydrated drift and gives every client one thing to render. Provider loop-ownership and tool-enforcement tiers already exist but are **undeclared** (claude_code_pty=enforced; codex=native-only via deny-all SDK handler; agy_cli=none, ignores tools) — a manifest lets the host stop lying. Session context-ownership is **implicit** today (agy_cli sets `omit_history`, codex omits when a thread exists) → make it one declared field.
- **Alternatives**: Keep StreamEvent canonical (rejected — every surface re-implements the reducer); infer behavior at runtime (rejected — fragile, the source of today's special-cases). Cite: `base.py:25-157`, `agents/types.py:101-424`, `aggregator.py:34-228`, `provider_sessions.py:29-138`, `channels/sse.py:42-83`.

## 5. Self-hosted substrates (Q1: default fully self-hosted)

- **Secrets**: **Self-host Infisical** via Docker Compose (Postgres+Redis+app) on the Hetzner host, behind Cloudflared/Tailscale (not public). Authenticate every machine surface with a **Machine Identity (Universal Auth)** → short-lived token; inject with `infisical run -- <cmd>`; never commit `.env`. **Keep two secret planes separate**: gateway/runtime keys (`AUTH_SECRET`, `WORKSPACE_ENCRYPTION_KEY`, `DATABASE_URL`, shared fallback provider keys) via Infisical; per-workspace/user provider keys stay in Pawrrtal's own encrypted store (`paw workspace env set`), NOT Infisical. Sandboxes get only minimal scoped env injected by the orchestrator at create time (no token baked into the image). *(Existing Bitwarden Secrets Manager `paw services` path must not be silently replaced.)*
- **Sandbox**: non-core, **off-by-default**. The **default driver is `local-confined`** — CWD confinement + network-off via OS primitives (bubblewrap on the Linux host, or a path-confinement wrapper in the tool-surface layer), no Docker/KVM/microVM/image. `docker-gvisor` (syscall wall, ms startup, no KVM), `kata-microvm` (KVM microVM), and `e2b` are **opt-in tiers** behind the same `sandbox:runtime` slot; `upstash-box` is opt-in only (managed-cloud, conflicts with self-hosted). Self-hosted E2B is still **not** a default (`e2b-dev/infra` is Apache-2.0 but GCP-first, Nomad+Consul+Firecracker, bare-metal/nested-virt, multi-node, ~2500GB/24vCPU — non-turnkey for one Hetzner box); E2B stays an opt-in substrate behind the same interface. One sandbox per conversation; exec streams over the SSE parts contract; pause = stop+commit / snapshot keyed to conversation; resume = restart from snapshot. **See ## Sandboxing posture** for the full driver tiers and the `SandboxRuntime` port.
- **Gateway**: **No external AI gateway.** Pawrrtal's own gateway (Story 3) is the single seam; CLI/PTY providers stay native under `providers/<provider>/` and are driven directly (an external gateway can't proxy them anyway and adds a rejected trust boundary).
- **Open**: confirm Hetzner KVM/nested-virt for the Kata tier; snapshot storage + GC policy for abandoned sandboxes; least-privilege per-sandbox secret scoping. Cite: `/root/.claude/skills/infisical-cli-secrets/cookbook/pawrrtal.md`, `github.com/e2b-dev/infra/self-host.md`, gVisor/Kata/Firecracker isolation comparisons.

## 6. Persistence + incremental migration

> **RE-SCOPED (files-first, no DB for app data):** Pawrrtal's app-data persistence is **pure files, NO database** — no Postgres, no SQLite, no Alembic, and no `@effect/sql` for app data. The relational direction in this section is retired for app data; it survives only as historical context for the strangler. **See ## Persistence: files vs DB** for the chosen design (`FileStore` over `FileSystem.ts` + `KeyValueStore.layerFileSystem`, JSONL transcripts, ripgrep search, git-repo data root).

- **App data = plain files, not a database** (`FileStore` over effect-smol `FileSystem.ts` + `KeyValueStore.layerFileSystem`). The earlier "Effect SQL (`@effect/sql`), not Drizzle" choice held only while a relational store was assumed; it is **dropped for app data**. No `@effect/sql`, no Postgres, no Alembic owning app schema. Drizzle (comcom style) was also evaluated and rejected (`docs/plans/2026-06-02-effect-ts-projects-pilot-approach.md`). Conversation history is append-only JSONL; profiles/projects/memory/config are JSON files; the data root (`$PAWRRTAL_DATA`) is a git repo for history/backups.
- **No schema-migration authority needed** for app data — the JSON/JSONL readers are the schema; there is no Alembic/Effect-migration step. (The Python strangler still runs Alembic only during the one-shot exporter that walks the old tables into files.)
- **Coexistence enabler (during migration)**: both backends still share the same `chat_messages` shape (provider-agnostic `content/thinking/tool_calls/timeline` JSON = "the source of truth for what the chat UI renders") and emit identical SSE frames; the one-shot exporter maps those rows 1:1 by `ordinal` into `messages.jsonl`.
- **Extraction order**: Projects (done) → read-only CRUD slices (workspaces, conversation metadata) on the same auth stack → **paw CLI rewrite** (pure HTTP client; validates contracts from the consumer side, zero kernel coupling; uses `effect/unstable/cli`) → message-write slices → **streaming chat/turn LAST** (provider fan-out + SSE; flip only after parity + harness gates).
- **Open**: error-body shape parity (status-code-only vs body adapter); per-conversation write-ownership lock during concurrent appends; paw rewrite scope (full port vs HTTP/SSE core first). *(The earlier relational open questions — Postgres timing/`PgClient`, SQLite-vs-Postgres dialect parity for `timeline`/`tool_calls` — are **moot** under the no-DB decision: there is no app-data SQL store. See ## Persistence: files vs DB.)* Cite: `backend-ts/apps/api/src/Modules/Projects/Repo.ts:4,59`, `backend/app/infrastructure/models/conversation.py`, `docs/plans/2026-06-02-effect-ts-projects-pilot-approach.md`.

---

## 7. Thin-core decomposition & conventions (nanoclaw · Eve · effect-smol · comcom)

- **Decision**: The end-state is a **thin *core*** (`@platform/*` foundation + a one-loop `kernel` + the `api-core` contract) surrounded by **many small uniform packages in clean namespace layers** (`@clients/*` for external SDKs/providers/integrations; `@pawrrtal/*` for product sub-domains) — *not* the 12-package domain-split sketched in §3, and *not* "few packages" either: **"thin" means thin core, not low package count**. Capabilities follow the **3-way rule** (user-added → DB rows · team-curated → declarative registry data · core → in-trunk code module · external SDK → a wrapper package). Partition by **code vs. data**, layer by **namespace**.
- **Rationale**: Both reference implementations converge on this and contradict the package-zoo instinct.
  - **nanoclaw** (`nanocoai/nanoclaw`) — a deliberate "anti-OpenClaw": a **2-package trunk** (host orchestrator + container runtime), the two hot files a ~350-LOC router and a ~480-LOC poll-loop; a new agent = DB rows + `container.json` + `CLAUDE.md` (zero kernel edits); tools = declarative objects; channels/providers self-register via barrels and live **out of trunk** on git branches, pulled in by `/add-*` skills ("skills over features" is the biggest thinness lever).
  - **Eve** (`vercel/eve`) — **one** runtime package (`eve`) + a thin helper; the kernel is one ~1.4–2k-LOC tool-loop; an agent is a **directory** of declarative config (`instructions.md`/`skills/*.md` = markdown data; tools/channels = one `defineX()` file each, filename = name); `eve build` compiles the dir into `.eve/` manifests (config is *generated*); **frontends fully decoupled** behind `/eve/v1/*` (session + NDJSON) consumed by a typed `eve/client` or `useEveAgent` — `apps/` is docs only.
  - **effect-smol HTTP fixtures** (`backend/vendor/effect-smol/ai-docs/src/51_http-server/`) — the canonical **`domain/` (Schema.Class + `Schema.TaggedErrorClass`) · `api/` (HttpApi contracts) · `server/` (impls)** split; PascalCase, entity-first, **no `index.ts` barrels**; `workspace:^` internal deps; per-package tests. *(effect-smol is the authoritative v4 source for the API; the conventions are confirmed against the real `comcom` — see below.)*
  - **comcom** (`/mnt/HC_Volume_105512717/dev/comcom`, an Effect monorepo of ~125 small packages) — proves "thin ≠ few packages": a tiny zero-dep `@platform/*` foundation; **one contract package** `@comcom/api-core` (per-module `Domain·Api·Errors·RpcProtocol`, no barrels, `exports: { "./*": "./src/*.ts" }`); `OpenApi.fromApi(Api)` → committed `openapi.json` → `@hey-api/openapi-ts` → the **read-only `@comcom/api-client` package** → `@comcom/app-core` → frontends (`@apps/{app,web,admin,mobile}`) that **never import `@apps/api`**; **15 uniform `@clients/*`** packages wrap external SDKs (incl. `@clients/ai-sdk`, `@clients/mcp`, `@clients/e2b`); a dedicated **`@comcom/agent-harness`** package (= our kernel); host modules = `Service·Repo·Policy·Http·Rpc`; one contract → **both HTTP (`Api.ts`) and Effect RPC (`RpcProtocol.ts`)**; and the **3-way capability rule** — user-added → DB rows (skills), team-curated → declarative registry data (`Integrations/Apps/*`, `Mcp/Catalog/Registry.ts`), core → code module.
- **Auto-generated OpenAPI + typed client (first-class)**: `HttpApiBuilder.layer(Api, { openapiPath: '/openapi.json' })` synthesizes the spec **from the `api-core` types** — errors' `httpApiStatus` → error responses, `HttpApiMiddleware.Service` `security: { bearer }` → security schemes, `OpenApi.annotations({ title, description })` → summaries; `HttpApiScalar.layer(Api, { path: '/docs' })` serves docs; `HttpApiClient.make(Api)` yields a typed client from the *same* contract. **No hand-written spec** — the contract is the one source of truth for server, docs, and every client. `backend-ts/apps/api/src/App.ts` already wires this.
- **Translation for Pawrrtal (refined)**: thin core (`@platform/*` + `@pawrrtal/kernel` (agent-harness: one loop + 3 ports) + `@pawrrtal/api-core` contract → HTTP + RPC + auto-OpenAPI + `@pawrrtal/api-client`); providers + integrations as uniform **`@clients/*`** packages (anthropic · gemini · xai · codex · e2b · infisical · fireflies · mcp · ai-sdk…); product sub-domains as small `@pawrrtal/*` packages (app-core, app-shared, sandbox, secrets, sync, transcription); `projects/conversations/settings` = host role-folders; capabilities by the **3-way rule** (user→DB · team→registry data · core→code). Clients (`apps/web` Next, `apps/mobile` Expo, `apps/paw`) consume the generated client only. **Start with few packages; grow one small package at a time.** The subtraction stories (#17–19) keep the core thin. The publishable unit = `kernel` + `api-core` + `@clients/*` + the `paw` agent group — see ## 16 Kernel-as-SDK for the SDK/app boundary, the public-API sketch, and the deferred-not-chosen publish posture.
- **Alternatives**: the 12-package split (§3, rejected — a folder reshuffle; both references prove the win comes from things being **out** of the kernel, as files/data/branches, not re-domained into packages). Cite: nanoclaw README + `src/router.ts` + `container/agent-runner/src/poll-loop.ts`; eve `packages/eve/src/harness/tool-loop.ts` + deepwiki; effect-smol `ai-docs/src/51_http-server/{10_basics.ts,fixtures/}`.

## 8. Deployment & client connection model (hermes-desktop · web/desktop/mobile on a remote VPS)

> **SUPERSEDED (auth/transport/exposure):** §8's auth/transport/exposure specifics are superseded by §§9–11 — Tailscale (`serve`, tailnet-only) replaces Cloudflare Access; profiles replace cookie+bearer login; Effect-RPC over WebSocket replaces the `desktop:apiFetch` HTTP-proxy + CORS + safeStorage-bearer + loadURL-local-Next machinery. §8's distribution/update (electron-builder, electron-updater, in-app update prompt) and the one-renderer/one-facade principle still stand.

- **Decision**: Backend stays on the **VPS** (one Cloudflared hostname today; the Effect backend later). The frontend ships as **(a) the website** — unchanged, same-origin, cookie auth via Cloudflared — and **(b) bundled app clients (desktop + mobile)** that call the *same* backend **cross-origin** via the generated **`api-client`** with **bearer tokens** + a configurable base URL + CORS. The `api-client` gets exactly two knobs every client sets: **a base URL** and **an auth-header injector**.
- **The one big change — auth.** Pawrrtal today is strictly same-origin: `frontend/lib/api.ts` has *no* base-URL concept (relative paths only), and auth is an HTTP-only **session cookie** (`credentials:'include'`) that "just works" because the browser and API share one Cloudflared origin. A **bundled** app runs on a custom scheme (`tauri://localhost` / `app://`), which is **not a secure http origin**, so the remote backend's `Set-Cookie` is dropped and CORS applies → move app clients to **bearer tokens (JWT access+refresh) in OS secure storage** (expo-secure-store mobile · Stronghold/keyring Tauri · safeStorage Electron). Backend adds a **token-issuing auth path** alongside cookie login, **CORS_ORIGINS** for the app origin(s), and accepts **both** during transition. **Mobile (Story 15) forces bearer regardless** — native apps can't ride browser cookies — so standardize on bearer across bundled clients; web keeps cookies.
- **Two shapes (we can do both)**: **Shape A (interim, zero auth change)** — the desktop/mobile webview *navigates to* the live remote https hostname, so the client IS a real https origin and same-origin cookies survive untouched; ship native chrome + auto-update around the deployed site fast. **Shape B (the decoupled end-state, FR-008)** — bundle the SPA locally and call the remote API cross-origin with bearer tokens; the only model that works for mobile and the one that matches the one-generated-client plan.
- **hermes-desktop's transferable pattern** (it's Electron, **desktop-only**, *not* a web+app dual-target — a reference for the *connection*, not the duality): the renderer makes **zero** direct HTTP calls — **all backend traffic goes through the Electron main process over IPC**, which resolves the base URL at runtime (local/remote/SSH modes), attaches the **bearer secret server-side** (the renderer only sees the key's *length*), and **relays SSE to the renderer** — so CORS/same-origin never apply and the secret never reaches the web layer. Backend URL is **runtime-configured in a Settings screen** and persisted (`desktop.json`), not a build-time env. Distribution = electron-builder per-OS installers + **electron-updater** auto-update via GitHub Releases. If Pawrrtal's shell is Electron this is a near-complete template; the *principles* (bearer in secure storage, configurable base URL, a native HTTP layer to dodge webview CORS) carry to Tauri/Expo too.
- **Reality check (corrects stale docs)**: the **`electron/` shell was removed** (Electron → Electrobun "zero-native Zig shell" → removed; a Tauri v2 sprint was *scrapped*). Only **`frontend/lib/desktop.ts`** (typed `window.pawrrtal` bridge with web-safe fallbacks) survives, and `frontend/lib/api.ts` has no base-URL seam. So the desktop shell is **greenfield**: pick **Tauri v2** (tiny binaries, also targets mobile, capabilities security — fits the self-hosted ethos, but custom-scheme origin makes bearer tokens mandatory) or **Electron** (heavier; mature session/cookie + `protocol.handle` + electron-updater; hermes is a ready template). Mobile = **Expo** either way.
- **Distribution/update**: Tauri Updater or electron-updater with an **in-app update prompt** (recorded user preference); code-signing/notarization required; CI on the self-hosted, OctavianTocan-gated runner. Mobile via EAS Build + EAS Update (OTA JS).
- **Reused**: `frontend/lib/desktop.ts` as-is for Shape A, extended with secure-storage methods for Shape B; the `api-core → api-client` seam (FR-007/008) — give it the base-URL + auth-injector knobs so every client differs only in those two values. Cite: `frontend/lib/api.ts`, `frontend/hooks/use-authed-fetch.ts`, `frontend/lib/desktop.ts`, `frontend/content/docs/handbook/deployment/vps-deploy.md`, hermes `src/main/{hermes,config}.ts` + preload; Tauri/Expo/Electron auth docs.
- **craft-agents-oss** (`craft-ai-agents/craft-agents-oss`, by craft.do — Pawrrtal's visual reference) is the **strong web+desktop** reference hermes lacked: **one React renderer, two shells**, where the frontend talks to **one injected facade** (`window.electronAPI`) generated from a single `CHANNEL_MAP` via `buildClientApi()` — **only the transport differs** per platform (Electron IPC vs a web WebSocket adapter); the web app literally reuses the desktop renderer (tsconfig alias + `lazy(import('@/App'))`, installing the web adapter *before* mounting). **Auth split confirmed**: web = cookie (rides the WS upgrade), desktop/CLI = **bearer token**, *the same server accepts both*, web stays same-origin (no CORS). **Local vs remote** via a `RoutedClient` that routes **per channel** — LOCAL_ONLY (OS/window/update) vs REMOTE_ELIGIBLE (sessions/files/LLM), mode chosen by env (`CRAFT_SERVER_URL` set → remote thin-client; unset → embedded local) — finer than an all-or-nothing base URL. Distribution = electron-updater + a *before-quit state-capture* hook so sessions restore after update.
- **Decisions locked (supersede the Shape A/B framing above).** Desktop = **Electron**; base URL = **runtime-configured** (Settings + `electron-store`); app auth = **bearer token**. For a **Next.js** frontend the clean shell is neither Shape A (remote-navigate — couples to VPS uptime, and Cloudflare Access blocks non-browser clients) nor a static `next export`/`file://` bundle (breaks App Router/RSC and `window.origin`), but **spawn the Next *standalone* server on a loopback port and `loadURL('http://127.0.0.1:<port>')`** — a real local http origin keeps SSR/routing/cookies intact, only `/api/*` goes remote (`next.config.ts` is already `output:'standalone'`). **API calls proxy through the Electron main process** (`desktop:apiFetch` IPC): main injects the **bearer token** (from `safeStorage`; gate on `isEncryptionAvailable()`, warn on Linux `basic_text`) + the **runtime base URL** → no CORS, token never in the renderer; access+refresh with single-in-flight refresh-on-401 in the proxy; login via system-browser/device-code. Backend adds **`HttpApiSecurity.bearer()` alongside** the cookie `session_token` so the *same* `/api/v1` endpoints accept either. SSE/chat: proxy over an IPC channel **or** a renderer fetch-stream with per-route CORS (decide per route). **Runtime config**: one `getApiBaseUrl()` resolver — web `''` (same-origin; never reintroduce web backend-URL selection), desktop = persisted; modes **Cloud | Local | Custom**; **optional local-backend mode** spawns FastAPI + health-polls `GET /api/v1/health` and flips the base URL only when healthy. The single facade is `frontend/lib/desktop.ts` (extend with config + token bridge methods). **Distribution**: electron-builder per-OS (mac dmg arm64+x64, win nsis, linux AppImage; `asar:true`) + electron-updater with an in-app `update-downloaded` → AppDialog prompt → `quitAndInstall()`; signed/notarized; on the OctavianTocan-gated runner (macOS notarize = the one `macos-latest` exception). **Reconcile first**: the stale `docs/superpowers/plans/2026-03-26-electron-desktop-app.md` (Vite + `file://` + cookie-domain hack + sidecar) is **superseded**; create the missing `electron/` workspace (`main.ts` spawn+loadURL · `server.ts` · `preload.ts` · `ipc.ts`).
- **Open (carry to the deployment slice)**: the Cloudflare-Access-admits-non-browser-client, FastAPI-bearer-path, and SSE-over-IPC-vs-CORS questions are **resolved by §§9–11** (tailnet `serve` replaces Cloudflare Access; profiles+bearer replace the cookie path; agent streams ride Effect-RPC over WSS, not IPC/CORS). Still open: does an `electron/` impl exist on another branch (referenced by `next.config.ts`/`dev-ports.ts`, absent on disk this session)? **macOS notarization runner** (the self-hosted pool is Linux).

## Consolidated open questions (carried into split specs)

1. effect version target: **beta.74 (backend-ts) vs beta.85 (use-agy)** — diff vendored revisions, pick one.
2. backend-ts **test-runner fix** (Roadmap Step 0) — how `@effect/vitest` suites collect + which duplicate test tree is canonical.
3. **Next migration slice** after Projects (likely conversations metadata).
4. Gateway external façade: **OpenAI vs Anthropic** dialect for v1 (internal parts map cleanly to Anthropic blocks; OpenAI is what ccpty/opencode_go already speak).
5. **Kata KVM availability** on the Hetzner plan; sandbox snapshot storage + GC.
6. **Parts backfill**: upcast old `{content,thinking,tool_calls,timeline}` rows to `parts[]`, or synthesize `parts[]` on read.
7. **Safety for AgentProviders**: which `AgentSafetyConfig` guards a loop-owning CLI honors (codex bypasses `run_model_tool_loop`).
8. **Per-profile password**: is an optional per-profile password **mandatory** once more than one human shares the tailnet (§11), or always optional?
9. **Profiles seed source**: a `profiles/` directory vs a single `profiles.yaml`; and is profile CRUD an **authed RPC surface** (who may create/rename/delete a profile)?
10. **Embeddings/vector storage under pure-files**: do semantic-search embeddings need a sidecar binary (e.g. a small vector file/index) or none at all (scan-only)? — the one place the no-DB decision (§12) might still pull in a non-file artifact.
11. **ACP adapter maturity per CLI**: validate that `claude-code-acp` and `codex-acp` actually expose enough of `session/request_permission` + `fs/*` + `terminal/*` to claim `tool_enforcement: enforced` (§15); Gemini CLI native ACP first.
12. **Migration exporter language**: write the one-shot table→files exporter in **Python** (live SQLAlchemy ORM, reads the real DB directly) vs **Effect** (re-implement table reads) — §12.
13. **SDK publish trigger** (§16): resolved *internal-now, publish-gated* — but the maintainer still green-lights the four gates (contracts API-frozen 2+ cycles · stable non-`unstable`/non-beta Effect pin · 2+ in-repo consumers through the generated contract · an external party asks) and must **define what "an external party asks" concretely means** before any release.
14. **SDK public scope/name at publish** (§16): keep the internal `pawrrtal`/`@pawrrtal/*` scope vs alias a vendor-neutral `agentkit` scope **at publish only** (do not squat a public name now) — decision deferred to publish-time.
15. **`@clients/*` ship scope** (§16): how much of `packages/clients/*` ships publicly — proposed a **curated starter subset** at publish (all wrappers live in `packages/clients` regardless of what publishes); which wrappers make the starter cut is open.
16. **SDK license** (§16): decided **at publish-time**, not now.
17. **Agent-definition discovery vs existing discovery** (§16): does the standalone filesystem agent-definition discovery (`instructions.md` + `agent.ts`, filename = identity) **unify with or duplicate** the existing manifest/plugin loader (§3) + `.agents/skills` discovery? Open whether it is one mechanism or two kept in sync.

---

## 9. Unified RPC layer (one Effect-`RpcGroup` contract, two transports, one bridge)

**Decision.** Define every app capability **once** as effect-smol `RpcGroup`s living beside the existing `@pawrrtal/api-core` HttpApi groups (same `Domain·Errors·RpcProtocol` discipline), and reach them with a single transport-agnostic `RpcClient`. Only the **protocol layer** changes per destination. This is the same `RpcProtocol.ts` "second transport" already promised in plan.md ("one contract → HTTP + Effect RPC + auto-OpenAPI + generated client") — now made the spine of the desktop/web/mobile client, replacing the hand-rolled `desktop:apiFetch` HTTP-proxy IPC of §8. **v1 transport = WebSocket/WSS to the tailnet node**; the local bundled-runtime MessagePort path is **designed-for but deferred past v1** (post-v1 local-first option, per program decision #3).

**Transports (all verified in `backend/vendor/effect-smol`):**

| Destination | Wire | Client layer | Server layer | Status |
|---|---|---|---|---|
| Remote tailnet backend (web · desktop-remote · mobile) | WebSocket / WSS to `*.ts.net` | `RpcClient.layerProtocolSocket` + `BrowserSocket.layerWebSocket(url)` | `RpcServer.layerProtocolWebsocket` | **v1 — chosen** |
| Local bundled runtime (desktop, optional) | Electron `MessagePort` | `RpcClient.layerProtocolWorker` + `BrowserWorker.layer((id)=>port)` | `RpcServer.layerProtocolWorkerRunner` + `BrowserWorkerRunner.layerMessagePort(port)` | **DEFERRED (post-v1 local-first)** |
| Plain CRUD, no streaming | one-shot HTTP | `RpcClient.layerProtocolHttp` | `RpcServer.layerProtocolHttp` | available |

Vendored proof points (cite, do not assume npm v3 paths):
- `packages/platform-browser/src/BrowserWorker.ts:69-71` — `layer(spawn: (id:number)=>Worker|SharedWorker|MessagePort)`; "raw `MessagePort` values can be supplied directly" (line 15). Transferables are moved into `postMessage`'s transfer list automatically. *(Used only by the deferred local path.)*
- `packages/platform-browser/src/BrowserWorkerRunner.ts:220` — `layerMessagePort(port: MessagePort|Window)` runs a runner over an explicit port. *(Deferred local path.)*
- `packages/platform-browser/src/BrowserSocket.ts:69` — `layerWebSocket(url, options?)` backs an Effect `Socket` with `globalThis.WebSocket`. *(v1 transport.)*
- `packages/effect/src/unstable/rpc/RpcClient.ts:1178,1359,989` — `layerProtocolSocket` / `layerProtocolWorker` / `layerProtocolHttp`; `supportsAck` defaults `true` (`:286`) on socket+worker (real client-ack backpressure; HTTP cannot).
- `packages/effect/src/unstable/rpc/RpcServer.ts:980,1185,1412` — `layerProtocolWebsocket` / `layerProtocolHttp` / `layerProtocolWorkerRunner`.
- `packages/effect/src/unstable/reactivity/AtomRpc.ts:145` — `AtomRpc.Service<Self>()` binds the RPC client reactively for the renderer.

**Why streaming must ride RPC, not raw IPC.** `ipcMain.invoke` is one request → one response (no streaming); `webContents.send` event spam has no backpressure or cancellation. Effect RPC streaming methods return a `Stream` with ack-based backpressure (`supportsAck`) and interrupt-based cancellation (an `Interrupt` request tears down the producer fiber) over both socket and worker protocols. Agent token streams go here.

**Electron topology (greenfield `electron/`).** For v1 the renderer connects over WSS; the validated `contextBridge` brokers a connection descriptor, not the data path. The MessagePort handoff below is the **deferred local-first** wiring (`MessageChannelMain` ports ARE `MessagePort`s, so they plug into the effect-smol browser worker layers with zero glue — recorded now so the future path is unambiguous):

```ts
// electron/src/main.ts — broker a port AFTER validating the frame  [DEFERRED local-first path]
const { port1, port2 } = new MessageChannelMain()
const runtime = utilityProcess.fork(path.join(__dirname, 'runtime.js'), [], { serviceName: 'PawrrtalRuntime' })
runtime.postMessage({ kind: 'renderer-port' }, [port1])          // → BrowserWorkerRunner.layerMessagePort
mainWindow.webContents.postMessage('runtime-port', null, [port2]) // → BrowserWorker.layer((_)=>port)

// electron/src/preload.ts — the validated handshake, never exposes ipcRenderer
contextBridge.exposeInMainWorld('pawrrtal', {
  isDesktop: () => true,
  getRuntimePort: () => ipcRenderer.invoke('pawrrtal:getRuntimePort'), // DEFERRED: returns transferred MessagePort
  getConnection: () => ipcRenderer.invoke('pawrrtal:getConnection'),   // { target, profileId, unlocked:boolean }
})
```

```ts
// renderer — same client code regardless of transport
const ProtocolRemote = RpcClient.layerProtocolSocket().pipe(
  Layer.provide(BrowserSocket.layerWebSocket(`wss://${fqdn}/rpc`)))     // tailnet WSS — v1
// DEFERRED (post-v1 local-first):
// const ProtocolLocal = RpcClient.layerProtocolWorker({ size: 1 }).pipe(
//   Layer.provide(BrowserWorker.layer((_) => runtimePort)))             // MessagePort
const Protocol = ProtocolRemote // v1 is remote-only; swap in ProtocolLocal when the local path lands
```

**`contextBridge` is the security floor + handshake, not the data layer.** Keep `contextIsolation:true, sandbox:true, nodeIntegration:false`; expose only a tiny validated `window.pawrrtal`; validate `event.senderFrame` in every main handler; never expose `ipcRenderer`. In v1 the bridge brokers only the connection descriptor + privileged native ops. The deferred local MessagePort is handed over **only after** frame validation, so that fast lane inherits the bridge's gating without its per-message structured-clone cost (electron/electron#27024: in-world port traffic is not re-serialized through the isolation boundary).

**Alternatives rejected.** electron-trpc / @egoist/tipc / Comlink as the primary RPC — they fork the type contract away from the Effect backend being migrated to; effect-smol's worker+websocket protocols give the same surface end-to-end (web→WS, desktop→WS in v1 / MessagePort when local lands, mobile→WS). Routing agent streams through `ipcMain.handle` (no streaming) or `webContents.send` (no backpressure) — rejected.

Sources: `https://www.electronjs.org/docs/latest/tutorial/message-ports`, `https://www.electronjs.org/docs/latest/api/utility-process`, `https://www.electronjs.org/docs/latest/tutorial/context-isolation`, `https://www.electronjs.org/docs/latest/tutorial/security`, `https://github.com/electron/electron/issues/27024`, `backend/vendor/effect-smol/packages/platform-browser/src/{BrowserWorker,BrowserWorkerRunner,BrowserSocket}.ts`, `backend/vendor/effect-smol/packages/effect/src/unstable/rpc/{RpcClient,RpcServer}.ts`, `backend/vendor/effect-smol/packages/effect/src/unstable/reactivity/AtomRpc.ts`, `frontend/lib/desktop.ts`.

---

## 10. Tailscale-exposed backend (replaces Cloudflare Access for the app/API)

**Decision.** Expose the backend over `tailscale serve` (tailnet-only HTTPS/WSS, real `*.ts.net` cert), **never `funnel`**, and bind the service to `127.0.0.1` only. Tailnet membership becomes the network access-control layer. This **supersedes the "one Cloudflared hostname protected by Cloudflare Access" model** (current workspace fact, FR-046, Constraints deployment bullet, §8) for the app/API surface. **Chosen path: tailnet-only, with NO public Cloudflared path for now** — the app and API are tailnet-only and a public website surface is **deferred, not chosen** (program decision #2).

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8000   # Python now; :8001 Effect post-parity
# node: pawrrtal-api.tailb0501a.ts.net  → https://pawrrtal-api.tailb0501a.ts.net
```

No Caddy Host/cookie fixup is needed for a JSON API (FastAPI does not Host-validate by default); add `header_up Host` only if a dev server rejects unknown Host headers. Verify-private before handing over any URL (hard gate): the public edge must be 403 and `tailscale funnel status` empty; curl the FQDN from another tailnet node (`openclaw-vps.tailb0501a.ts.net` / `100.105.205.85`) to confirm it serves.

**Killer feature — spoof-proof identity headers.** When `serve` proxies a request it injects and **strips client copies of** `Tailscale-User-Login` (e.g. `alice@example.com`), `Tailscale-User-Name`, `Tailscale-User-Profile-Pic`. Because the backend is loopback-bound, nobody can hit `:8000` directly to forge them, so the backend **trusts** them as the human's identity (Open WebUI uses exactly this for password-less auto-login). This is what lets Pawrrtal drop traditional auth (§11).

**Client discovery + connection.**
- Web build keeps same-origin (`getBackendBaseUrl()` → `''`). Native shells get an **absolute** tailnet base URL `https://<node>.tailb0501a.ts.net` (RPC over `wss://<node>.tailb0501a.ts.net/rpc`), runtime-configured (mirror hermes' `normaliseRemoteUrl()` — strip trailing `/` and a trailing `/v1`).
- A device **must run the Tailscale client** (no embeddable userspace tailscaled in a sandboxed app for user laptops/phones). Electron → Tailscale desktop app installed + logged in; Expo → Tailscale iOS/Android VPN. Ship a "connect" screen that probes `GET /api/v1/health` over the tailnet and tells the user to start Tailscale on failure.
- Userspace `tailscaled --tun=userspace-networking` is the **backend-host** option for tun-less containers, not a way to make a phone app a node; the Hetzner VPS is a normal host (kernel mode fine).

**Exposure options (both recorded; chosen = Option 1 for v1):**

| | Option 1 — fully tailnet-gated (**chosen for v1; app + API only**) | Option 2 — split surfaces (public website) — **DEFERRED** |
|---|---|---|
| Cloudflare Access | **gone** for app/API | gone (website would be public-by-design) |
| App + API | direct `*.ts.net`, no Cloudflared in path | tailnet-only via `serve` |
| Public site | **none** — no public Cloudflared path now | static Next pages/docs/sign-up via Cloudflared; "Open the app" → join-tailnet / open desktop app |

Either way Cloudflare Access as the auth gate disappears. **v1 ships Option 1** (app + API tailnet-only, no public surface). A public brochure path (Option 2) is **deferred, not chosen** — record it as a future option, not v1 scope.

**Security posture.** Network layer = tailnet membership (IdP auth + machine-key enrollment + optional device approval). App layer = ACLs/grants restricting which tailnet devices/tags reach the node's port. The backend listens only on `127.0.0.1`, so the sole path in is `serve`. An attacker needs a compromised enrolled node key OR full IdP auth into *your* tailnet + device approval + any ACL — the port is never on the public internet, unlike a Cloudflare-Access-fronted login.

Sources: `https://tailscale.com/kb/1242/tailscale-serve`, `https://tailscale.com/docs/concepts/tailscale-identity`, `https://github.com/tailscale-dev/id-headers-demo`, `https://docs.openwebui.com/tutorials/auth-sso/tailscale/`, `/root/.claude/skills/tailscale/cookbook/{serve-vs-funnel,expose-app-privately,sandbox-userspace}.md`, `frontend/lib/api.ts`, `frontend/content/docs/handbook/deployment/vps-deploy.md`.

---

## 11. Profiles instead of login (retires FastAPI-Users, session cookie, ALLOWED_EMAILS)

**Decision.** Replace account login with a hermes-desktop / OpenClaw **profiles** model: the backend lists profiles, the user selects one, an **optional** per-profile password unlocks it, and requests carry `X-Pawrrtal-Profile: <id>` (+ `Authorization: Bearer <profileToken>` only for password-locked profiles). Tailnet membership (§10) is the network access layer; `Tailscale-User-Login` is *who the human is*; profile selection is *which workspace*. No app-level cookie or session JWT.

**Flow.**
1. App reads its stored backend FQDN, probes `GET /api/v1/health` over the tailnet.
2. `GET /api/v1/profiles` (unauthenticated at the app layer — tailnet already gated) → `[{ id, displayName, avatarUrl?, requiresPassword }]`, seeded from `profiles.yaml` or a `profiles` dir.
3. User picks a profile (a picker, like hermes' switcher).
4. If `requiresPassword`: `POST /api/v1/profiles/{id}/unlock {password}` → backend verifies an Argon2/bcrypt hash → short-lived **opaque bearer**. Else: selection alone is identity.
5. Requests carry `X-Pawrrtal-Profile` always + bearer only when locked. On desktop the **main process** holds the token and attaches it (renderer sees only a boolean `unlocked`, copying hermes' `apiKeyLength`-only exposure). On web: in-memory / `sessionStorage`.
6. Backend resolves identity per request: `Tailscale-User-Login` → human; `X-Pawrrtal-Profile` → workspace; verify `profileToken` only if locked.

The per-profile secret lives **server-side only** (`{ id, displayName, password_hash?, allowed_logins?[] }`); the app never stores a password, only the returned token. Bearer (header), not cookie: native shells have no cookie jar worth depending on, cross-origin `*.ts.net` makes cookie `SameSite`/`Domain` fiddly, and a header is trivial to attach in main while keeping it out of the renderer.

**Effect middleware shape (reuses the strangler scaffolding verbatim — only the credential source changes):**
```ts
export class ProfileMiddlewareService extends HttpApiMiddleware.Service<...>()(
  'ProfileMiddlewareService',
  { error: AuthenticationError, requiredForClient: false,
    security: { profileToken: HttpApiSecurity.bearer } } // optional; locked profiles only
) {}
// runtime: read Tailscale-User-Login + X-Pawrrtal-Profile, resolve via ProfileStore → provide CurrentUser.
```

**What this retires (exact paths):**

| Layer | Removed / replaced |
|---|---|
| Python | `backend/app/infrastructure/auth/users.py` (FastAPI-Users: `UserManager`, `CookieTransport(session_token)`, `JWTStrategy`, `auth_backend`, `fastapi_users`, `current_active_user`, `get_allowed_user`/`ALLOWED_EMAILS`) → `app/profiles/` (model + `GET /profiles`, `POST /profiles/{id}/unlock`) + a `current_profile` dep. `auth/dev_login.py`, `auth/oauth/router.py` (app login + Google/Apple) gone (model/provider OAuth under `app/providers/` stays). `config.py`: drop `allowed_emails*`, `cookie_*`, `auth_secret`, `pawrrtal_enable_dev_login`, `admin_email/password`; repurpose/drop `backend_api_key`; add `profiles_config_path` / `allowed_tailscale_logins`. |
| Effect (backend-ts) | `packages/api-core/src/Modules/Auth/Api.ts`: swap `HttpApiSecurity.apiKey({in:'cookie',key:'session_token'})` → header-trust or `HttpApiSecurity.bearer`; `AllowedUserMiddlewareService` → optional per-profile login allowlist. Keep `Errors.ts` (`AuthenticationError` 401 / `AuthorizationError` 403). `apps/api/src/Modules/Authentication/{SessionStore,Http}.ts`: replace cookie→`GET :8000/users/me` with a native `ProfileStore` resolving `X-Pawrrtal-Profile` → `CurrentProfile`/`CurrentUser`. Middleware ordering note holds (authentication outer, allowlist inner). `Domain.ts` `User`/`CurrentUser` stays; populate from profile + `Tailscale-User-Login`. |
| Frontend | `frontend/lib/api.ts`: drop `API_ENDPOINTS.auth.{login,devLogin,devLoginBrowser,register,logout,me}`, add `API_ENDPOINTS.profiles.{list,unlock}`. `frontend/hooks/use-authed-fetch.ts`: drop `credentials:'include'` and the `401→router.replace('/login')` branch (lines ~29,34-43); on 401-from-locked-profile prompt unlock; attach `X-Pawrrtal-Profile` (+ bearer on desktop via the facade). `frontend/lib/desktop.ts`: add a `profiles`/`connection` bridge group (`listProfiles`, `getActiveProfile`, `setActiveProfile`, `unlock`, `getBackendUrl`, `setBackendUrl`) — renderer gets booleans/lengths, never the token. Remove `LoginForm`/`/login`/`/signup` and `frontend/middleware.ts` cookie redirect; add a profile-picker screen. |

**Reconcile with the in-flight auth strangler.** Finish the cookie-session slice **as a learning exercise** (teaches HttpApiMiddleware, `HttpApiSecurity`, `CurrentUser` provision, `SessionStoreError → AuthenticationError`, middleware ordering). It is **superseded for production**: a follow-up "profiles" slice reuses the same scaffolding, swapping `apiKey(cookie)`→`bearer`/none and `SessionStore`→`ProfileStore`.

Sources: `https://github.com/fathah/hermes-desktop` (`src/main/{profiles,config,hermes}.ts`), `/mnt/HC_Volume_105512717/services/hermes/.hermes/profiles/*/profile.yaml`, `https://docs.openclaw.ai/concepts/{agent-workspace,multi-agent}`, `https://tailscale.com/docs/concepts/tailscale-identity`, `backend-ts/packages/api-core/src/Modules/Auth/{Api,Errors}.ts`, `backend-ts/apps/api/src/Modules/Authentication/{SessionStore,Http}.ts`, `backend/app/infrastructure/auth/{users,dev_login,oauth/router}.py`, `backend/app/infrastructure/config.py`, `frontend/{lib/api.ts,hooks/use-authed-fetch.ts,lib/desktop.ts}`.

---

## 12. Persistence: pure files, no database

> **⚠️ SUPERSEDED (2026-06-27).** This entire section is **superseded** by the ADR `frontend/content/docs/handbook/decisions/2026-06-27-rivet-postgres-electric-hatchet-substrate.mdx`. The chosen substrate is **per-conversation Rivet actors** (running Pi unforked) for live session state, **Postgres** as the API-owned queryable record, **Electric** for read-path sync, and **Hatchet** for system-level durable work — not files-first. The reference-survey reasoning below (Craft Agents / Hermes / flue) is retained as historical context for *why* the team first leaned no-DB and what changed (audience growth, multi-device live sync, and v1 search pulled the decision to a Postgres-backed substrate).

**Decision.** *(superseded — see banner)* Make plain files the **sole source of truth** for everything (profiles, projects, conversation transcripts, memory, agent/workspace state, config). **There is NO database — no Postgres, no SQLite, no Alembic, no `@effect/sql` for app data, and no derived SQLite search index.** Search is **ripgrep/scan over the JSONL** (`messages.jsonl`); the slower-search-at-scale tradeoff is **accepted** (program decision #4). This re-scopes the prior persistence research (§6, "Effect SQL not Drizzle, Alembic owns the schema"): §6's relational direction is **retired** for app data; the source of truth is files, and there is no index to keep.

**Rationale (reference survey).** Every reference app that leans local converges on a similar split — agent definitions + human-readable artifacts = files; conversation history = append-only log; the only divergence is whether they additionally keep a DB *index* (hermes does; Craft Agents proves you do not need one). Pawrrtal chooses the no-DB end of that spectrum.

| App | Source of truth | Format | History / search | DB? |
|---|---|---|---|---|
| **craft-ai-agents/craft-agents-oss** | Files | JSON config + **JSONL** sessions + AES-GCM creds under `~/.craft-agent/` | Full history as JSONL; search = scan | **No DB at all** |
| **fathah/hermes-desktop** | Hybrid | YAML/`.env`/JSON files + **SQLite** `state.db` under `~/.hermes/` | **SQLite FTS5** for resume + search | **Yes — only** for FTS5/resume |
| **vercel/eve** | Agent=files; runtime=durable checkpoints | `agent/{instructions.md,tools/,skills/,…}` | Vercel Workflows checkpointing | Not exposed |
| **withastro/flue** | Agent=files; runtime=**append-only event log** behind pluggable adapter | Markdown agents/skills; `PersistenceAdapter` | **Durable Streams** replay; `sqlite()`/`@flue/postgres`/DO-SQLite | Optional/pluggable; default in-memory SQLite (ephemeral) |

Craft Agents proves you can ship a full agent desktop with **zero DB** — that is the model Pawrrtal adopts. (Hermes is recorded accurately as using a SQLite FTS5 index for its search/resume UX, but Pawrrtal's decision is no-DB; slower scan-based search is the accepted cost.) Flue/eve prove conversation history is naturally an **append-only event log** (a JSONL file IS a Durable Stream).

**Pawrrtal already has the files seam.** `backend/app/infrastructure/models/workspace.py:42` (`Workspace.path` → host dir with `.agent/` tree); `backend/app/workspace/filesystem.py` (`safe_child()` traversal guard at line 12, `build_tree()` at line 40 — reuse, do not reinvent). `ChatMessage` (`conversation.py:118`, ordered by `ordinal`, carrying `content`/`thinking`/`tool_calls`/`timeline`) is already an append-only ordered log → maps 1:1 to JSONL by `ordinal`.

**On-disk layout** (`$PAWRRTAL_DATA`, e.g. `~/.pawrrtal/`):

```
~/.pawrrtal/
  config.json                      # global app config (non-secret)
  profiles/
    <profile-slug>/
      profile.json                 # display name, avatar, created_at
      auth.json                    # optional password hash (argon2) + params  ← profiles-auth substrate
      preferences.json             # was UserPreferences
      personalization.json         # was UserPersonalization
      appearance.json              # was UserAppearance
      memory.jsonl                 # append-only typed proactive memory (was `memories`)
      projects/
        <project-slug>/
          project.json             # was `projects` row
          conversations/
            <conversation-id>/
              meta.json            # `conversations` row (title, labels, model_id,
                                   #   provider_session_*, channel keys, flags)
              messages.jsonl       # append-only `chat_messages` (Durable Stream)
              attachments/
      conversations/               # unattached chats (project_id == NULL)
        <conversation-id>/{meta.json, messages.jsonl, attachments/}
      workspaces/
        <workspace-slug>/          # == today's Workspace.path; .agent/ tree unchanged
  .git/                            # data root is a git repo (versioned backups/history)
```

**Hard requirements addressed.**
- *Search*: **ripgrep / scan over `messages.jsonl`** (Craft-Agents style). No index file. This is viable single-user; the **slower-search-at-scale tradeoff is accepted** as the cost of a zero-DB design.
- *Concurrent writes*: conversations are append-only JSONL → concurrent appends from web/Telegram/Google Chat are safe with `O_APPEND` + a per-conversation advisory lock (writers only append, no row contention). `meta.json` mutations are last-writer-wins via atomic temp+rename.
- *Backups/history*: the data root (`$PAWRRTAL_DATA`) is a **git repo** — versioned, diffable transcripts, rsync/Tailscale-friendly.
- *Migration off SQLAlchemy*: one-shot exporter walks the tables → `conversations`→`meta.json`, `chat_messages` (ordered by `ordinal`)→`messages.jsonl`, `projects`→`project.json`, `memories`→`memory.jsonl`, `user`/`user_profile`/appearance/preferences→`profiles/<slug>/…`; `workspaces.path` dirs move under `profiles/<slug>/workspaces/`. **Alembic stops owning app data entirely** — schema lives in the JSON/JSONL readers; there is no remaining "migration" step.

**Effect v4 mapping (grounded in vendored effect-smol).**
- `backend/vendor/effect-smol/packages/effect/src/FileSystem.ts` — first-class Effect module (node live layer). Build a core-light **`FileStore`** service on it: `readFileString`, append for JSONL, `makeDirectory`, atomic temp+rename for `meta.json`. No new dependency.
- `backend/vendor/effect-smol/packages/effect/src/unstable/persistence/KeyValueStore.ts` — already ships `layerMemory` (329) and **`layerFileSystem(directory)`** (361, one file per key, backed by `FileSystem` + `Path`). Use `layerFileSystem(dir)` as the backing for per-profile/per-project config blobs; cite it instead of hand-rolling. (Do **not** use `layerSql`.)
- Composition in `Modules/Layers.ts`: a single `FileStore` service (core, light). Conversation read/write and search all go through `FileStore` (search = scan); there is no `SearchIndex`/`@effect/sql` service to wire.

**Rejected.** A relational SQLite/Postgres source of truth (couples app correctness to migrations; fights files-first/profiles/Tailscale; no local-leaning reference app does this), **and** the optional derived SQLite FTS5 index (dropped deliberately — the slower scan-based search is the accepted cost of a fully no-DB design).

---

## 13. Removing Docker

**Decision.** Remove all app-serving Docker. Keep the Docker **engine** on the host only as the substrate for explicitly non-core, opt-in tiers (self-hosted Infisical, the Docker+gVisor sandbox tier). A clean install runs chat with no Docker present.

**Repo audit (confirmed).**

| Path | Services / role | Verdict |
|---|---|---|
| `docker-compose.yml` | `postgres` + `backend` + `postgres_data`/`workspace_data` volumes | **Delete** |
| `docker-compose.dev.yml` | `postgres` + `backend` | **Delete** |
| `docker-compose.demo.yml` | `postgres` + `backend` + demo volumes | **Delete** |
| `backend/Dockerfile` | Python FastAPI image | **Delete** (Python retired; Effect runs as a plain Bun process on the tailnet) |
| `frontend/Dockerfile` | Next.js image | **Keep only if** a containerized web deploy is still wanted; otherwise delete (desktop ships via Electron's local Next standalone server, plan §8) |

**Rationale.** Files-first + no-DB + Tailscale-direct dissolves the reason the compose stack exists: there is no Postgres service to orchestrate, the backend is reachable over the tailnet directly, and the data root is a git repo (not a `postgres_data` volume). No compose file currently references Infisical (grep returned nothing) — self-hosting Infisical via Docker Compose is a *future* substrate (research §5), so it does not constrain deleting the current app compose. After removal, the Docker engine is **not** a hard dependency of the core; it survives on the host purely for: (a) self-hosting Infisical (research §5), and (b) the `docker-gvisor` opt-in sandbox tier (see § Sandboxing posture). Both are non-core and opt-in.

---

## 14. Sandboxing posture

**Decision.** Sandboxing is a **non-core, off-by-default capability** behind the existing `sandbox:runtime` slot (`data-model.md:26`). The **default driver is `local-confined`** — CWD confinement + network-off via OS primitives (bubblewrap on the Linux host, or a path-confinement wrapper in the tool-surface layer), **no Docker / KVM / microVM / image**. `docker-gvisor`, `kata-microvm`/`e2b` are **opt-in tiers** a power user selects per conversation; Upstash Box is an opt-in driver only (managed-cloud, conflicts with self-hosted).

**Rationale (survey).**

| App / Tool | Sandbox tech | Default posture |
|---|---|---|
| **Craft Agents OSS** (closest analog: Electron, chat-first, trusted local) | **None** — permission modes + diff transparency only | No sandbox; "ask" mode is the default |
| **Vercel eve** | Pluggable `agent/sandbox/*` (Firecracker cloud; Docker/microsandbox/**just-bash** local) | Lightest local backend = just-bash (no container) |
| **Flue** | Sandbox is first-class; **default = in-memory just-bash** | Lightest possible; microVM/container backends opt-in |
| **Claude Code** | OS-level (macOS Seatbelt / Linux **bubblewrap**); FS limited to CWD, network via proxy only | Reduces permission prompts ~84%, not microVM-grade |
| **OpenAI Codex CLI** | macOS Seatbelt / Linux **seccomp+landlock**; **network OFF by default** | Workspace-scoped + network-off; full access is the opt-out |
| **Docker+gVisor / Kata / E2B / Upstash Box** | syscall wall / microVM / Firecracker / managed | **Never** a default anywhere surveyed; opt-in isolation tiers |
| **ACP** | N/A — execution safety explicitly delegated to implementations | Confirms sandboxing is an impl concern, not protocol/core |

Two philosophies split by product shape: **chat-first/desktop/local-first apps** (Craft Agents) lean on permission gates + transparency, *not* technical isolation; **code-execution-as-a-feature apps** treat the sandbox as a swappable adapter and still pick the lightest viable default, reserving microVMs for opt-in untrusted code. Nobody hardwires a microVM into the core or makes it the everyday default.

**Decision frame for Pawrrtal.** Threat model = trusted users (spec.md:15,22); the only residual risk a sandbox addresses is agent/model-written code being wrong/destructive on the host — a code-safety concern. So:
- *Core?* No — violates the `agent-core` MUST-NOT-import-a-sandbox-runtime invariant (`data-model.md:28`) and the light-core thesis.
- *Deferred entirely?* No — the spec leans on the sandbox for Story 16's runtime-availability guarantee and as the workspace successor; a *contract* should exist.
- *Optional, off-by-default — chosen.* Define the slot now, ship a trivial local default, make heavy drivers opt-in.

**Minimum safe default (`local-confined`, no microVM/container).** CWD confinement for `read_file`/`write_file`/`bash` (writes outside refused) + network-off for shell/code (Codex's biggest cheap prompt-injection win) + permission/diff transparency (Craft Agents' actual mechanism). Implemented with bubblewrap on the Linux host or a path-confinement wrapper in the tool layer — no daemon, no image.

**Opt-in tiers (same slot):** Tier 1 `docker-gvisor` (syscall wall, ms startup, no KVM); Tier 2 `kata-microvm`/`e2b` (dedicated-kernel; **confirm Hetzner KVM/nested-virt first** — research §5 open question); Tier 3 `upstash-box` (managed-cloud-only, conflicts with self-hosted Q1, opt-in only).

**Abstraction (sandbox provider interface, no SDK imports in the port):**

```ts
// contract (api-core / kernel protocols) — the slot: sandbox:runtime
interface SandboxRuntime {
  create(opts: { conversationId; image?; env?; network?: "off"|"egress" }): Effect<SandboxSession, SandboxError>
}
interface SandboxSession {
  exec(cmd: string, opts?): Stream<ExecChunk>   // streams over the existing SSE message-parts contract
  readFile(path): Effect<bytes>
  writeFile(path, bytes): Effect<void>
  pause(): Effect<SnapshotRef>                   // stop+commit / microVM snapshot keyed to conversationId
  resume(ref): Effect<void>
  destroy(): Effect<void>
}
// session record: { conversation_id, runtime, state: created|running|paused|destroyed, snapshot_ref? }
```

Drivers: `LocalConfinedRuntime` (default), `DockerGvisorRuntime`, `KataRuntime`, `E2BRuntime`, `BoxRuntime`. Only the port + `LocalConfinedRuntime` reference impl live near core; every heavyweight driver is a plugin package. Selection by slot, never by name. Every non-local driver ships `plugin.json` with `default: false` (extension-boundaries plugin rules). Secrets per research §5 (minimal scoped env at create time, nothing baked into the image). `exec` output rides the existing streamed message-parts/SSE contract (no new transport) — satisfies Story 4's live-output requirement.

**Spec tension (resolved).** An earlier draft had a heavier default than the chat-first + trusted-user model warrants — `data-model.md`'s Sandbox entity once read `Default runtime = docker-gvisor` and FR-021 once mandated a microVM-class default for all agent-generated code. Both are now reconciled to this section's decision: the contract is core; the **default driver is `local-confined`**; `docker-gvisor`/`kata`/`e2b` are **opt-in** tiers (Upstash Box opt-in only). This preserves Story 16's runtime-availability win and resumable boxes without making heavy isolation the cost of entry for a chat product.

---

## 15. ACP: controlling sub-agents

**Decision.** Introduce ACP (Agent Client Protocol) as a single **non-core `@clients/acp` Effect package** + one host-side **AgentProvider** adapter, treated as the **successor** to the hand-rolled CLI bridges (`agy_cli`, eventually `claude_code_pty`), not a fourth parallel one.

**What ACP is.** "LSP for coding agents" (Zed, Aug 2025): JSON-RPC 2.0, normally over stdio (HTTP/WS WIP), where a **Client** drives a whole external coding **Agent** subprocess that *owns its own loop*. Lifecycle: `initialize` → `session/new`/`session/load` → `session/prompt` with `session/update` notifications streaming the agent's `plan`/`agent_message_chunk`/`agent_thought_chunk`/`tool_call`/`tool_call_update`/`usage_update`, ending in `PromptResponse{stopReason}`. The Client implements callbacks the agent calls back into: **`session/request_permission`** (approve a tool call), **`fs/read_text_file`**/**`fs/write_text_file`**, and **`terminal/*`**. ACP *embeds* MCP (`session/new` carries `mcpServers`) — it sits one layer up, treating "an entire agent" as the unit instead of "a tool".

**ACP vs MCP.**

| Axis | MCP | ACP |
|---|---|---|
| The "server" | a tool/context provider | the agent itself (the whole harness) |
| Who drives whom | agent calls out to MCP servers | client drives the agent, consumes its loop |
| Granularity | one tool/resource | one end-to-end turn (plan + thoughts + many tool calls) |
| Pawrrtal analogue | `AgentTool` surface | **AgentProvider** role |

**Ecosystem.** Zed (native client + protocol author); Gemini CLI (first native ACP agent); Claude Code via `@zed-industries/claude-code-acp`; Codex via `codex-acp`; Cursor/Copilot/Cline/OpenHands + ~30 others; official TS SDK `@agentclientprotocol/sdk` + Rust SDK. **Targets in order:** Gemini CLI (native ACP) first, then Claude Code via `@zed-industries/claude-code-acp`, then Codex via `codex-acp`.

**Why it beats today's bridges.** Pawrrtal drives external CLIs three ad-hoc ways (`backend/app/providers/`): `agy_cli` (one-shot `--print`, stdout/log scraping; its docstring admits **no ACP** and a `--sandbox` boundary gap; `tool_enforcement: none`), `claude_code_pty` (an OpenAI-shim ModelProvider-in-disguise), `openai_codex` (cleanest; `native-only` via deny-all SDK handler). ACP collapses these into **one** typed, streaming, permission-aware client — write one ACP client and get Gemini CLI, Claude Code, Codex, and 30+ future agents as **registry data rows**, not new provider classes.

**Where it lives (3-way rule: external SDK → `@clients/*` package).**

```
backend-ts/packages/clients/acp/        # @clients/acp ; no index.ts barrel, exports: "./*"
  src/
    Client.ts      # AcpClient: spawn subprocess, JSON-RPC over stdio, newSession/prompt/cancel;
                   #   exposes Stream<AcpUpdate, AcpError>
    Config.ts      # AcpAgentConfig: command, args, cwd, env, advertised capabilities
    Errors.ts      # AcpSpawnError, AcpProtocolError, AcpAuthError, AcpTimeoutError
    Schema.ts      # Effect Schema for consumed wire types (ContentBlock, SessionUpdate,
                   #   ToolCall, RequestPermission, StopReason) — decode at the boundary
    Registry.ts    # DATA: known agents → launch spec
```

Workspaces currently glob `packages/*` + `apps/*` (`backend-ts/package.json`) — **widen to `packages/clients/*`** or place at `packages/clients-acp`. The host adapter (the AgentProvider that registers it) lives under `apps/api/src/Modules/` (sibling to `Authentication`/`Projects`/`System`), analogous to how Python `openai_codex/provider.py` is the host provider over the Codex SDK.

**AcpClient (Effect shape).** Use the official `@agentclientprotocol/sdk` as the JSON-RPC engine, wrapped in Effect — `@effect/platform` `Command` to spawn (`gemini --experimental-acp`, `npx @zed-industries/claude-code-acp`, …) with `cwd` = the conversation workspace; `Stream` for `session/update`; `Scope`/`acquireRelease` so the subprocess is always reaped; tagged `Errors`. Do **not** hand-roll JSON-RPC framing (repo's "check official docs/SDK first" rule).

**Mapping onto existing contracts.**
- `session/update` variants → unified `parts[]`: `agent_message_chunk`→text, `agent_thought_chunk`→reasoning, `tool_call`/`tool_call_update`→tool (with status), `plan`→plan, `usage_update`→usage, `PromptResponse.stopReason`→done. No new event vocabulary.
- ACP `sessionId` → opaque provider-session handle per `contracts/session-record.md` (mirrors `provider_sessions`); resume via `session/load` when `loadSession` is advertised.
- Permission: implement the Client side of `session/request_permission` against Pawrrtal's own approval policy — three modes: auto-deny (safest default; matches codex today), policy-mapped (`allow_once`/`reject_once`), human-in-the-loop (bubble to the Pawrrtal user over the **RPC layer** to the renderer and relay the answer). `fs/*` + `terminal/*` callbacks run against the **Pawrrtal workspace/sandbox** — so the sub-agent's access is mediated by Pawrrtal's boundary, not the CLI's own (fixes the agy_cli `--sandbox` gap).

**CapabilityManifest the host adapter declares:**

```
role: AgentProvider
tool_enforcement: enforced     # ← FIRST AgentProvider that can honestly claim this,
                               #   because the host implements request_permission + fs/terminal callbacks
streaming_tier: incremental    # real session/update deltas
session_model: provider-session
reasoning: summary|raw         # agent_thought_chunk
multimodal_in: per agentCapabilities.promptCapabilities.image
safety_honored: subset         # agent owns its loop; permission gate + fs/terminal sandbox ARE Pawrrtal-enforced
```

**Registry data (team-curated → registry data).** `{ id: "gemini-cli", command: "gemini", args: ["--experimental-acp"] }`, `{ id: "claude-code-acp", command: "npx", args: ["@zed-industries/claude-code-acp"] }`, `{ id: "codex-acp", … }`. Adding an agent = a data row (the catalog pattern already used for models in `backend/app/providers/catalog/`), not a new provider class.

**Supersedes.** `backend/app/providers/agy_cli/` stdout/log scraping (retire); over time, fold `claude_code_pty` toward ACP once `claude-code-acp` is wired. Prefer ACP over raw PTY for anything that speaks it; keep PTY only for agents with no ACP adapter.

---

## 16. Kernel-as-SDK: a standalone agent-building library + CLI

> **Status: GO-LATER.** Build the SDK *boundary* **now** as internal workspace-protocol packages; **defer** the npm publish behind four gates. Publishing is **DEFERRED, NOT CHOSEN** (phrased like the deferred-website decision in §10) — the publishable unit ships internally in v1 and nothing goes public yet. This **refines §§3 and 7** (it names the publishable unit and locks the dependency arrow) and adds **no new architecture** — the thin core already specced IS the SDK; we name it publishable-shaped and build-enforce the app→SDK arrow.

- **Decision**: Extract the thin core into a standalone, eventually-publishable **SDK + CLI** that the app depends on (the eve/Flue framework-vs-app relationship), with Pawrrtal-the-app as the flagship consumer. In Flue vocabulary: **FRAMEWORK** = the publishable surface (`kernel` + `api-core` + the `@clients/*` wrappers + the `paw` AGENT group); **HARNESS** = the kernel (one loop + ports); **RUNTIME** = `apps/api` + `$PAWRRTAL_DATA` + Tailscale + profiles + Effect-RPC + the external façade. The dependency arrow is **app-depends-on-SDK, build-enforced** — the sentrux/import-boundary rule (§3) promoted from a lint warning to a **physical wall** (Story 1's demand). Keep the `pawrrtal`/`@pawrrtal/*` scope internally; **do not squat a public name** (a vendor-neutral `agentkit` scope may be aliased only **at publish**).
- **Why GO-LATER (calibrated to a solo maintainer + trusted users)**: ~90% of the benefit is the **package boundary already planned**; the npm release adds only cost until the gates clear. Costs of publishing now, grounded in repo:

  | Cost of publishing now | Evidence in repo |
  |---|---|
  | Semver-as-promise on a still-moving contract | `data-model.md` open questions: parts backfill, the ACP `enforced` claim (§15), per-profile auth (§11) |
  | A **beta** substrate | `effect@4.0.0-beta.74` under `effect/unstable` (`backend-ts/package.json`); `use-agy` pins beta.85 — unreconciled |
  | Two-masters tension | the loop wanting profiles/files/tailnet identity leaks app specifics or bends the flagship |
  | Docs/support with zero users | trusted-user, single-operator scope (`spec.md:15`) |
  | N = 1 consumer (Rule of Three) | only `apps/api` exists today |

- **The four publish gates** (release only when **all** clear): (1) the four shared contracts **API-frozen for 2+ cycles**; (2) a **stable, non-`unstable`/non-beta Effect pin**; (3) **2+ in-repo consumers** through the generated contract; (4) **an external party asks**. The **Effect `beta.74`-vs-`beta.85` reconciliation is elevated to a PUBLISH BLOCKER** (the internal boundary still picks one pin now, per §2/open-Q1).
- **Boundary — SDK owns vs Pawrrtal-app owns** (the locked split; the GATEWAY is the only entity that straddles it):

  | Concern | SDK owns (generic, eventually publishable) | Pawrrtal-app owns |
  |---|---|---|
  | Loop | the turn loop + compaction | — |
  | Contracts | the four (`Part`/`PartDelta` fold invariant · ModelProvider/AgentProvider + `CapabilityManifest` · `SessionRecord` single context-owner · the gateway **internal** parts envelope) | — |
  | Ports | the ports as **interfaces only** (Provider, ToolRegistry + permission-check, Channel, SandboxRuntime, FileStore/SessionStore, Secret, Memory, Observability) + **trivial reference impls** (`LocalConfinedRuntime`, node-FS FileStore, dev provider stub) | concrete impls of **every** port |
  | Persistence | the persistence **PORT** + JSONL helpers | the `$PAWRRTAL_DATA` layout + git data root + ripgrep search + exporter |
  | Wrappers | the `@clients/*` wrappers (anthropic/gemini/xai/codex/ai-sdk/mcp/acp/e2b/fireflies) on `@platform/*` | heavy sandbox drivers (docker-gvisor/kata/e2b/upstash-box) |
  | Generation | contract→HTTP/RPC/typed-client generation | — |
  | CLI | the `paw` **AGENT** command group | the `paw` **OPERATOR** command group |
  | Data | — | catalog/registry **DATA** rows |
  | Identity/transport | — | Profiles · `tailscale serve` + `Tailscale-User-Login` trust · the v1 WebSocket transport (+ deferred MessagePort) · Electron/Expo shells · Infisical · OTel wiring · web/mobile/channels/active-recall |
  | **Gateway (the only split entity)** | internal envelope = SDK | external OpenAI/Anthropic **façade** = app |

  **Rule**: if it changes when you add an agent/provider/channel/tool → it's a **wrapper, registry data, or a file** (NOT the SDK); if it's *this-tailnet/this-profile/this-`$PAWRRTAL_DATA`* specific → it's the **app**.

- **Public API sketch (SDK; frozen only at the publish gate)**: `defineAgent({ model, instructions, tools?, skills?, sandbox? })`; `run`/`stream` (require a Provider + ToolRegistry); `defineTool` with **Effect Schema**; the ports as `Context.Tag` services (Provider, ToolRegistry, SandboxRuntime with a `LocalConfinedRuntime` default, FileStore, Channel, Secret, Observability); the contract types `Part`/`PartDelta`/`CapabilityManifest`/`SessionRecord`; filesystem discovery of an agent project. **Acceptance**: a two-file project (`instructions.md` + `agent.ts`) runs via `paw run` over a **local FileStore + one provider** with **NO gateway/profiles/Tailscale** — proving Story 1's "runs-with-no-capabilities" at the package level.
- **CLI — ONE `paw` binary, two groups (do NOT split)**: the **AGENT** group is **kernel-only by construction** (the SDK surface) = `new`, `dev --no-ui`, `run --payload`, `build`, `info` (`run --payload` is the CI primitive + the non-HTTP dispatch entry on the same kernel); the **OPERATOR** group is the Pawrrtal HTTP/RPC client = `verify`, `lab`, `live-ops`, `profiles`. A command tree is cheap to version; the agent group stays kernel-only by construction; **alias it as an `agentkit` bin at publish**.
- **Packages / first mechanical step**: keep the `pawrrtal`/`@pawrrtal/*` scope internally. Layout (only `api-core` + `apps/api` exist today; the rest are NEW): `packages/platform` (zero internal deps), `packages/kernel` (one loop + compaction + ports; imports nothing concrete), `packages/api-core` (EXISTS), `packages/api-client` (NEW, generated), `packages/clients/*` (NEW wrappers), `apps/api` (EXISTS — host: profiles/Tailscale/`$PAWRRTAL_DATA`/façade/channels), `apps/paw` (NEW; today Python at `backend/app/cli/paw`), `apps/web` + `apps/mobile` (NEW). The **publishable unit (internal in v1)** = kernel + api-core + clients + the paw agent group. **First mechanical step**: widen `backend-ts/package.json` workspaces to include `packages/clients/*` and add `kernel` + `platform`. Workspace-protocol deps, catalog versions, **no index barrels**.
- **Deferrable defaults (locked now)**: gateway external façade = **APP** (only the internal envelope is SDK); `@clients/*` ships as a **CURATED STARTER SUBSET** at publish (all live in `packages/clients` regardless of what publishes); **public package name + license = decided AT publish-time**; the Effect-pin reconciliation = **publish blocker** (boundary still picks one now).
- **Precedent comparison**:

  | Reference | Shape | Lesson for Pawrrtal |
  |---|---|---|
  | **Claude Agent SDK** | harness library; Claude Code the product on the same harness | extracted **after** the loop hardened — the right ordering (mirrors GO-LATER) |
  | **OpenAI Agents SDK** | tiny library-only surface | lowest churn; small public surface wins |
  | **Mastra / VoltAgent** | core packages vs Cloud/VoltOps | clean OSS-vs-commercial split |
  | **LangChain / LangGraph** | OSS cores vs LangSmith | the API-churn cautionary tale — reinforces freezing contracts before publish |
  | **Astro Flue** | files/markdown agent on a separate Pi core; pluggable `PersistenceAdapter`; Pi not marketed standalone | copy the shape, leave the stack |
  | **Vercel eve** | agent = a directory, but Vercel IS the platform (conflated to sell hosting) | copy the ergonomics, avoid the substrate and the publish-to-sell-hosting posture |

  **Universal caveat**: every 2026-era agent framework is **pre-1.0**, which independently reinforces the deferral.
- **What to copy / what to leave**: **Copy** — filesystem-first agent definition (filename = identity; markdown skills under `.agents/skills`, which Pawrrtal already uses); the tiny `define*` surface; named adapter ports; a channel-independent session/stream contract (Effect-RPC over WS is the analogue of eve's session route + NDJSON, §9); durable park/continue/terminate; the `paw` verbs. **Leave** — eve's managed durable-execution dependency (Pawrrtal does park/resume over its **pure-files** SessionStore/EventStreamStore; `messages.jsonl` already IS the event log, §12); Flue's stack (use **Effect Schema**, not valibot); the multi-deploy-target matrix (one runtime today — build the agent-definition + ports now, defer a second target).
- **Alternatives**: publish now (rejected — semver-as-promise on a beta substrate with N=1 consumer; ~90% of value is the boundary, not the release); never extract (rejected — the boundary is the thin core §§3/7 already demands, and build-enforcing the arrow is free). Open items carried to the consolidated list: items **13–17** (publish trigger + "an external party asks" definition · public scope/name · `@clients/*` ship scope · license · agent-definition discovery unify-or-duplicate).

Sources: repo — `specs/003-pawrrtal-overhaul/{spec,plan,research,data-model}.md` + `contracts/`; `backend-ts/package.json` (`effect@4.0.0-beta.74`); `backend/app/cli/paw`; `backend/vendor/effect-smol`. External — Vercel eve docs; `flueframework.com` + `withastro/flue` + the Cloudflare Flue post; Claude Agent SDK docs; `openai-agents-js`; Mastra + VoltAgent; the LangChain-vs-LangGraph comparison; the eve-vs-Flue comparison; the Rule of Three.
