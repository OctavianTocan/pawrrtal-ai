# Feature Specification: Pawrrtal Platform Overhaul (North-Star Umbrella)

**Feature Branch**: `003-pawrrtal-overhaul`

**Created**: 2026-06-23

**Status**: Draft (umbrella — to be split into per-feature specs before planning)

**Input**: User description: "A really huge spec with all the stuff I told you, instead of all these splits. We can split it later."

> **What this document is.** A single umbrella/program spec capturing the **entire** intended Pawrrtal overhaul and north-star vision in one place, so the whole picture is legible without hopping between fragments. It is written at **north-star end-state** altitude (the ideal capability, implementation-agnostic) and is **meant to be decomposed** into smaller per-feature specs before any `/speckit-plan`. Each user story is tagged `[covers …]` with its source inventory item(s) and the future split-spec letter, so splitting later is mechanical.
>
> Two of these areas already have detailed standalone specs drafted earlier: **`001-claude-agent-sdk-streaming`** (Story 7) and **`002-telegram-visual-harness`** (Story 11). They remain as the first two "splits" of this umbrella.
>
> **Audience & scale:** built for a handful of **trusted** self-hosted users (the maintainer and a few others). Tenants are assumed trusted, so adversarial cross-tenant isolation is out of scope for now; opening to untrusted/public multi-tenancy is an explicit later effort, not designed-for today. (Agent/model-generated code is still sandbox-isolated regardless — that's a code-safety concern, not a tenant-trust one.)

## Clarifications

### Session 2026-06-23

- Q: Default deployment posture, given several attractive substrates (Upstash Box, an AI Gateway, Infisical Cloud) are managed/hosted? → A: **Default fully self-hosted** — managed services only where there is no practical self-hostable option (self-hosted Infisical, own-infra/local sandboxes, no external gateway dependency); hosted substrates are opt-in only.
- Q: Multi-tenant trust model for bring-your-own-bot and per-user sandboxes? → A: **Trusted users only** for now — tenants are assumed trusted, adversarial cross-tenant isolation is out of scope, and opening to untrusted/public multi-tenancy is an explicit later effort (accepted as later rework). Agent/model-generated *code* stays sandbox-isolated regardless of tenant trust.
- Q: Is the Python→TypeScript/Effect migration total, or are Python carve-outs allowed? → A: **Total** — no Python remains in the end-state; the backend moves entirely to **Effect v4 (effect-smol)**. Exact v4 style reference: **`../use-agy`** (maintainer-provided), plus `comcom` and vendored `backend/vendor/effect-smol`.
- Q: Anything explicitly out of scope for the whole overhaul? → A: **Nothing** — the 16 stories are the complete intended set; finer scope is bounded per split spec.

### Session 2026-06-24

- Q: How is the backend reached and who is "the user," now that there's no public login? → A: **Tailnet-only Tailscale access** — the backend is exposed via `tailscale serve` (tailnet-only, never `funnel`), bound to loopback, **replacing Cloudflare Access**. Identity is **profiles, not login**: the backend trusts the spoof-proof `Tailscale-User-Login` header; a profile may carry an optional password whose unlock returns a short-lived opaque bearer. **FastAPI-Users, the `session_token` cookie, and `ALLOWED_EMAILS` are retired.** (See FR-046, FR-047.)
- Q: Is there a public website / marketing surface in v1? → A: **Deferred** — the app + API are tailnet-only; a public surface is recorded as a later effort, not chosen now (no Cloudflared brochure path).
- Q: How does the desktop app reach the backend? → A: **Desktop is remote-only for v1** — the Electron renderer uses **one Effect-RPC client over WebSocket** to the tailnet backend; the local bundled-runtime (MessagePort) path is designed-for but **deferred past v1**. Streaming rides Effect `Stream`, not `ipcMain.invoke`/`webContents.send`. (See FR-048.)
- Q: How is application data persisted? → A: **Pure files, no database at all** — conversations (`meta.json` + append-only `messages.jsonl`), profiles, projects, memory, and config are plain files under a single `$PAWRRTAL_DATA` git-repo root; search is ripgrep/scan over the JSONL (slower-at-scale tradeoff accepted); **no Postgres/SQLite/Alembic** for app data.
- Q: What is the default sandbox tier? → A: **`local-confined` by default** (constrained CWD + network-off, no container/microVM); microVM-class tiers (Docker + gVisor, Kata, E2B) and managed-cloud (Upstash Box) are **opt-in**, non-default drivers. (See FR-021.)
- Q: How do external coding-agent CLIs plug in? → A: **ACP as a non-core `@clients/acp` capability** — the Agent Client Protocol becomes the successor to the hand-rolled CLI bridges, wrapped as an Effect package plus one host-side AgentProvider adapter, with host-enforced permission + fs/terminal callbacks.
- Q: Should the kernel become a standalone publishable agent SDK + CLI (Eve/Flue-style)? → A: **GO-LATER** — build the SDK boundary **now** as internal workspace-protocol packages with a **build-enforced app→SDK arrow** (the app depends on the SDK; the SDK imports no app/runtime code) and `paw`'s **dual agent/operator roles** (one binary, a kernel-only agent group + a Pawrrtal-client operator group). **DEFER the npm publish** (deferred-not-chosen, like the website) behind **all four** gates: contracts frozen 2+ cycles · a stable non-beta Effect pin · 2+ in-repo consumers through the generated contract · an external ask. The **gateway façade = app**; the **internal parts envelope = SDK**. (See FR-009, SC-020, and the Constraints/Out-of-Scope SDK-boundary entries.)

## User Scenarios & Testing *(mandatory)*

> Stories are coherent **capability areas**, prioritized by sequencing as much as importance (P1 = foundational backbone the rest builds on). "User" is, by area, an end chatter, the maintainer/operator, or the coding agent.

### User Story 1 - A tiny, reliable core that is a standalone agent-building SDK (Priority: P1)

*[covers #13 → future Epic K]*

The thin core is not just *Pawrrtal's* kernel — it is a **standalone, eventually-publishable agent-building SDK + CLI**, and **Pawrrtal is its first consumer**. The layering is named explicitly: a generic **framework/harness/runtime** (one readable turn loop — build context → call provider → dispatch tools → emit parts → park/continue/terminate — plus compaction, the four shared contracts, and the ports as interfaces only) lives *below* the Pawrrtal **app/host**, and the dependency arrow is **build-enforced one-way: the app depends on the SDK; the SDK imports no app/runtime code**. Around the kernel sit a **thin foundation and a small set of packages in clean namespace layers** (the `@platform/*` foundation, the one-loop `kernel`, the `api-core` contract, the generated `api-client`, the uniform per-SDK `@clients/*` wrappers, and a few product packages), where **capabilities are added as data or small uniform packages — never by fattening the core**: external SDKs/providers/integrations are uniform wrapper packages; team-curated catalogs (providers, integrations, MCP) are declarative registry data; user-added skills/agents are stored rows injected at runtime; only core business is in-trunk code. The partition is **code vs. data** — generic loop machinery is SDK; anything *this*-agent / *this*-provider / *this*-channel specific is config. Adding a capability is "**drop a file**," never "edit the kernel." Pawrrtal-specific concerns (profiles, Tailscale trust, the `$PAWRRTAL_DATA` layout, the external OpenAI/Anthropic façade, channels) stay in the app *above* the SDK boundary. *(This supersedes an earlier instinct to split the backend into ~12 domain packages — a folder reshuffle, not a thin core; references: nanoclaw, Eve.)*

**Why this priority**: This is the architectural backbone the entire vision rests on. The gateway, sandboxes, transcription, OpenClaw/Mirage plugins, and the migration all assume this thin-core SDK + plugin shape, with the app sitting on top of it as a consumer.

**Independent Test**: Add a new tool/provider/channel as a discovered file and confirm it appears in the running system with **zero edits to the kernel**; confirm the SDK alone (kernel + contracts + ports + one provider) compiles and runs a minimal turn with no Pawrrtal app code installed; confirm the build fails if the SDK imports any app/runtime module.

**Acceptance Scenarios**:

1. **Given** a new tool, provider, or channel, **When** it is added as a discovered file/data, **Then** it appears in the running system with **zero edits to the kernel**.
2. **Given** the kernel's dependency graph, **When** examined, **Then** it imports no concrete provider/channel/tool/SDK and no app/runtime module — only the contracts and the narrow ports; the build **fails** if the app→SDK arrow is reversed.
3. **Given** the kernel alone, **When** run with no capabilities installed, **Then** it still runs a minimal agent turn.
4. **Given** the SDK boundary (kernel + `api-core` + one provider + the `paw` agent command group), **When** a scaffolded **two-file** project (`instructions.md` + `agent.ts`) is run via `paw run`, **Then** it runs a real agent turn over a local FileStore with **NO gateway, profiles, or Tailscale** — proving the SDK stands alone without any Pawrrtal service.

---

### User Story 2 - One TypeScript / Effect codebase, one `paw` with two roles (Priority: P1)

*[covers #14, #10 → future Epic L; CLI is the pilot]*

The backend is migrated **completely** from Python to **TypeScript on Effect (v4 / effect-smol)** — no Python remains in the end-state — modeled on the maintainer's Effect-v4 references (`../use-agy` for exact style, plus `comcom`), so the whole stack (backend, CLI, web, mobile) converges on one language and one set of patterns. The **`paw` CLI is rewritten in Effect as the pilot/proof** — and it is **one binary with two command groups** that mirror the SDK/app split: an **AGENT group** (`new`, `dev --no-ui`, `run --payload`, `build`, `info`) that is **kernel-only by construction** — the SDK surface, with no dependency on any Pawrrtal HTTP/RPC service — and an **OPERATOR group** (`verify`, `lab`, `live-ops`, `profiles`) that is a **Pawrrtal HTTP/RPC client**. `run --payload` is the **CI primitive *and* the non-HTTP dispatch entry on the same kernel** (the headless way to feed a turn without standing up the gateway). The CLI is therefore the **dogfood-by-extraction proof of the SDK boundary**: if the agent group runs without the operator group, the kernel really is standalone. At publish, the agent group is aliased as an `agentkit` bin.

**Why this priority**: The substrate decision shapes how every other capability is ultimately built. Doing the CLI first de-risks the larger migration, yields an early self-contained win, and the agent/operator split is the first place the SDK→app boundary is exercised end-to-end.

**Independent Test**: The CLI runs fully on the Effect/TS package with parity to today's verification flows, while the rest of the system keeps working; the **agent group runs with zero Pawrrtal services** (no gateway/profiles), and `run --payload` dispatches a turn without any HTTP server — proving the kernel-only group is genuinely kernel-only and the migration can proceed incrementally without a big-bang cutover.

**Acceptance Scenarios**:

1. **Given** the Effect CLI package, **When** the existing end-to-end verification flows are run through the **operator group**, **Then** they pass with parity to the current CLI.
2. **Given** the **agent group** (`new`/`dev`/`run --payload`/`build`/`info`), **When** invoked, **Then** it drives the kernel directly with **no Pawrrtal HTTP/RPC service** required.
3. **Given** `paw run --payload <turn>`, **When** dispatched, **Then** the kernel runs the turn headlessly (no gateway) — the CI primitive and non-HTTP dispatch entry are the same path.
4. **Given** the migration in progress, **When** a backend capability is moved to Effect, **Then** the system keeps working throughout (no all-or-nothing cutover).

---

### User Story 3 - Use any model or CLI harness through one normalized gateway (Priority: P1)

*[covers #23, #20, the gateway/bidirectional-session idea, part of #1 → future Spec S]*

Pawrrtal exposes **one normalized gateway** that can drive any model **or any full agent CLI** (Claude Code, Grok, Codex, Antigravity, …) behind a stable contract — internally a rich streamed parts model, externally an OpenAI/Anthropic-compatible API. The gateway is the **only split entity** across the SDK/app boundary: the **internal parts envelope is part of the SDK contract** (the kernel emits and folds it), while the **external OpenAI/Anthropic-compatible façade is an app/edge projection that sits *above* the SDK** — a translation layer over the channel-deliver seam, owned by the Pawrrtal host, not by the kernel. The implementation behind a given model (`-p` print mode, an SDK, a local HTTP bridge, a real API) is a **swappable detail**. Each backed model **honestly declares its capabilities and enforcement level** (tools: enforced / native-only / none; streaming tier; session model) so the picker never over-promises. Pawrrtal's own tools are injected through each CLI's tool seam where possible. **Sessions are bidirectional**: Pawrrtal can hand a session to a CLI and resume it, and CLI-native sessions can be surfaced through Pawrrtal — with a single **context-owner-of-record** per session so the two never desync.

**Why this priority**: This is the unification that answers "what is Pawrrtal." It is the seam all providers terminate at and what makes the system substrate-agnostic; keeping the external façade above the SDK is what lets the kernel stay a publishable, app-free unit.

**Independent Test**: Drive two different CLIs through the gateway, get one normalized stream from each, and confirm each model's declared capability/enforcement manifest matches what it can actually do; resume a session on one of them.

**Acceptance Scenarios**:

1. **Given** two CLIs with different tool/output mechanisms, **When** each is driven through the gateway, **Then** both produce the same normalized streamed output and a truthful capability manifest.
2. **Given** a model swaps its underlying mechanism (e.g. `-p` → SDK), **When** clients call it, **Then** nothing observable changes for them.
3. **Given** a multi-turn conversation, **When** a turn resumes, **Then** exactly one side owns the context and the session does not double or diverge.
4. **Given** the SDK contract, **When** the external OpenAI/Anthropic-compatible façade is examined, **Then** only the internal parts envelope lives in the SDK; the façade is an app/edge projection over the channel-deliver seam and is not imported by the kernel.

---

### User Story 4 - Run agents and CLIs in disposable sandboxes (Priority: P1)

*[covers the sandbox idea; dissolves #5 → future Spec T]*

The agent can **spin up an isolated sandbox** to do work or to run a full CLI, then tear it down. The sandbox **substrate is pluggable** behind one slot, with a **`local-confined` default** (constrained CWD + network-off via OS primitives — no container/microVM/image) and **opt-in** heavier tiers (Docker + gVisor, Kata, E2B; managed-cloud Upstash Box opt-in only). When a CLI/runtime is provisioned inside its sandbox tier, **"runtime not present in production" failures disappear**, isolation supplements the removed permission gating, and each session/tenant is isolated. A paused/snapshotted sandbox can be keyed to a conversation so a session is, optionally, a resumable box.

**Why this priority**: Sandboxing is the safety substrate once gating is removed (Story 6), the fix for the runtime-availability class of bug, and the isolation layer for multi-tenancy. It is reused by the gateway (Story 3).

**Independent Test**: Have the agent create a sandbox, run a CLI/command inside it with live-streamed output, then destroy it; confirm host isolation and that the substrate can be swapped.

**Acceptance Scenarios**:

1. **Given** a task needing isolated compute, **When** the agent requests a sandbox, **Then** one is provisioned, runs the work with streamed output, and is cleaned up.
2. **Given** a CLI whose runtime is not on the host, **When** it runs inside its provisioned sandbox tier, **Then** it works — no "runtime not found."
3. **Given** the substrate is changed, **When** the same task runs, **Then** behavior is equivalent (substrate is a detail).

---

### User Story 5 - Every secret via Infisical, none in plaintext (Priority: P1)

*[covers #15 → future Spec M]*

**All** secrets — provider keys, user bot tokens, OAuth tokens, database and service credentials — are sourced through **Infisical**, with **no secrets in plaintext** anywhere (no committed `.env`, no plaintext config). Secrets are injected into the app, the CLI, CI, and into sandboxes securely.

**Why this priority**: Foundational and security-critical; it is the secure home for Story 13's user bot tokens and every provider credential, and it should be in place before more credential-bearing features land. Low-throughput, survives the migration almost unchanged.

**Independent Test**: Audit the repo and running config for plaintext secrets (expect zero), and confirm each surface (app, CLI, CI, sandbox) obtains its secrets from Infisical at run time.

**Acceptance Scenarios**:

1. **Given** the repository and deploy config, **When** scanned, **Then** no secret is present in plaintext.
2. **Given** any surface that needs a secret, **When** it runs, **Then** the secret is resolved through Infisical, not a checked-in file.

---

### User Story 6 - Shed the dead weight (Priority: P2)

*[covers #17 (permissions), #18 (budget), #19 (telemetry + workspaces) → future subtraction specs]*

Unused/peripheral systems are **removed before the migration**, so we port a thin, clean core rather than dead code: the **fine-grained permission system** (and `permissions.md`), all **budget** machinery, and **telemetry + workspace** systems — while **logging is kept**, and observability is redone properly later in Effect. Safety shifts from gating to **isolation** (Story 4), and per-session sandboxes succeed the workspace concept.

**Why this priority**: Deleting unused systems shrinks the surface the migration must carry and simplifies several other stories (notably the Claude provider, which no longer needs a permission bridge). Removals are low-regret and migration-aligned.

**Independent Test**: Confirm the permission, budget, telemetry, and workspace systems are gone, logging still works, and no remaining feature silently depends on the removed systems.

**Acceptance Scenarios**:

1. **Given** the permission/budget/telemetry/workspace systems, **When** removed, **Then** the app still runs and logging is intact.
2. **Given** a feature that referenced a removed system, **When** exercised, **Then** it behaves correctly without it (or is updated to not need it).

---

### User Story 7 - Claude as a first-class streaming model (Priority: P2)

*[covers 001 — already specified in `specs/001-claude-agent-sdk-streaming/`]*

Claude (via the Agent SDK) is selectable as a model that streams live like Claude Code — text, reasoning, and tool steps — across surfaces, under the same safety guarantees as other models, alongside the existing Claude Code PTY option. (Detailed acceptance criteria live in spec 001; simplified by Story 6's removal of the permission system.)

**Why this priority**: A concrete, high-value provider that exercises the gateway (Story 3) and validates the streaming/parts contract. Already specified.

**Independent Test**: See `specs/001-claude-agent-sdk-streaming/spec.md`.

**Acceptance Scenarios**:

1. **Given** a Claude model, **When** a turn runs, **Then** it streams incrementally and renders like Claude Code. *(Full set in spec 001.)*

---

### User Story 8 - A clean model catalog and one reasoning-effort knob (Priority: P2)

*[covers #2 → future Spec B]*

Each model appears **once** in the picker, not duplicated per reasoning effort. Reasoning depth is a **separate, explicit knob** (the existing effort control) that changes the same model's thinking — so "Gemini 3.5 Flash (Low/Medium/High)" collapses into one entry plus an effort selector.

**Why this priority**: Directly fixes a visible confusion in the model picker and sets the clean pattern any new models (including Claude) follow.

**Independent Test**: Open the model picker and confirm one entry per model with a working reasoning-effort selector that changes thinking depth without spawning duplicate entries.

**Acceptance Scenarios**:

1. **Given** a model that supports multiple reasoning depths, **When** shown in the picker, **Then** it appears once with an effort knob, not as several look-alike entries.
2. **Given** an effort level is chosen, **When** a turn runs, **Then** the model's thinking depth changes accordingly.

---

### User Story 9 - Reliable provider auth and configuration (Priority: P2)

*[covers #1, #8 → future Spec C]*

Provider authentication is **reliable and clearly configurable** — specifically the Antigravity/Google path that currently fails with "Antigravity CLI auth unavailable: CLI refresh failed," and a documented way to **configure Google login**. When auth is unavailable, the system fails clearly and falls back gracefully rather than dead-ending a turn.

**Why this priority**: A provider that fails most of the time is a daily blocker; auth reliability is table-stakes for the providers the gateway exposes.

**Independent Test**: Configure the Antigravity/Google login per the documented path and send a message that succeeds; then break the credential and confirm a clear failure + graceful fallback (not a dead turn).

**Acceptance Scenarios**:

1. **Given** valid Google/Antigravity credentials configured the documented way, **When** a turn runs, **Then** it succeeds without auth-refresh errors.
2. **Given** missing/expired credentials, **When** a turn runs, **Then** the user gets a clear message and a graceful fallback.

---

### User Story 10 - Memory that works with any model (Priority: P2)

*[covers #3, #7 → future Spec D]*

Active recall is **model-agnostic** — it routes through the provider abstraction rather than being hardwired to one model/API — and its prompt is **tightened so it produces nothing unless the user's message genuinely needs recalled information** (no more noise on every turn).

**Why this priority**: Memory runs on every turn; if it's noisy or tied to one provider it degrades every conversation and blocks provider flexibility.

**Independent Test**: Run active recall with two different selected models (it works for both), and confirm it stays silent on messages that don't call for recalled info and surfaces useful info when they do.

**Acceptance Scenarios**:

1. **Given** any selected model, **When** a turn runs, **Then** active recall functions through the provider abstraction (not a hardwired model).
2. **Given** a message that needs no recalled information, **When** processed, **Then** active recall produces nothing.

---

### User Story 11 - Trust what you see (visual verification harness) (Priority: P2)

*[covers #4/#4a/#4b, 002 — already specified in `specs/002-telegram-visual-harness/`]*

The agent and maintainer can capture what messages **actually look like** on a surface (incl. live streaming states and time-delayed flows like reminders) and compare against a **human-approved golden reference library**, so "it works" is grounded in real rendering. (Detailed criteria in spec 002.)

**Why this priority**: This is how every rendering story (12) and provider story (7) is actually verified; it closes the agent's blind spot. Already specified.

**Independent Test**: See `specs/002-telegram-visual-harness/spec.md`.

**Acceptance Scenarios**:

1. **Given** a flow, **When** captured, **Then** the real rendering is compared to its golden reference. *(Full set in spec 002.)*

---

### User Story 12 - A great chat surface (Priority: P3)

*[covers #4c (rich media), #11 (verbosity toggles) → future Specs E, I]*

Telegram (and other surfaces) get **rich-media** rendering for bot messages (making use of the platform's rich-media support), and **per-category verbosity toggles** via inline keyboard — the user can independently show/hide tool calls, thinking, active-recall output, etc., instead of a single numeric verbosity level.

**Why this priority**: Presentation quality and control over what's shown; verified directly by Story 11's harness.

**Independent Test**: On Telegram, toggle individual categories (tool calls, thinking, …) on/off and confirm each independently shows/hides; send a message that uses rich media and confirm it renders richly.

**Acceptance Scenarios**:

1. **Given** the verbosity toggles, **When** the user turns off "tool calls" only, **Then** tool calls are hidden while thinking/answers remain per their own toggles.
2. **Given** a message with rich media, **When** delivered, **Then** it renders using the surface's rich-media capabilities.

---

### User Story 13 - Your bot, your account, zero web (Priority: P3)

*[covers #9 → future Spec F]*

A user can **bring their own Telegram bot** (provide a token; the system uses that bot bound to their account), and **set everything up entirely via API/CLI** — creating accounts and linking Telegram **without touching the web app**, so the maintainer can provision themselves and others headlessly. User bot tokens are stored securely (via Story 5).

**Why this priority**: Headless, multi-bot onboarding is how the maintainer sets up real users without a web flow; it's also the first real multi-tenancy surface.

**Independent Test**: From the CLI/API only, create an account, link a user-provided Telegram bot token, and exchange messages through that bot — never opening the web app; confirm the existing official-bot path still works.

**Acceptance Scenarios**:

1. **Given** only the CLI/API, **When** the maintainer provisions an account and links a custom bot token, **Then** the user can chat through their own bot without using the web app.
2. **Given** a user-provided bot token, **When** stored, **Then** it is held securely (no plaintext) and used only for that account.

---

### User Story 14 - Pluggable agent capabilities (Priority: P3)

*[covers #16 (transcription/Fireflies), #12 (OpenClaw), #22 (Mirage) → future Specs N, J, R]*

New agent capabilities plug onto the deep plugin system (Story 1): a **transcription service** with pluggable backends (e.g. Fireflies) that can transcribe a voice note or a URL like YouTube; **support for OpenClaw plugins**; and **Mirage** so agents can browse through anything. Each is a layered package, not a core change.

**Why this priority**: These are the proof-cases that shape the plugin contract and expand what agents can ingest/do; they're valuable but depend on the plugin system being real.

**Independent Test**: For each capability, install it as a plugin and exercise it (transcribe a voice note/URL; run an OpenClaw plugin; have an agent browse via Mirage) without modifying the core.

**Acceptance Scenarios**:

1. **Given** the transcription plugin, **When** a voice note or supported URL is sent, **Then** a transcript is produced via the selected backend.
2. **Given** the OpenClaw and Mirage plugins, **When** installed, **Then** their capabilities are available to agents through the plugin surface.

---

### User Story 15 - Pawrrtal on the phone (Priority: P3)

*[covers #21 → future Epic Q]*

A **mobile app** (React Native / Expo) is a first-class client alongside web and Telegram, consuming the same backend contract and rendering the same streamed parts model, so a person can use Pawrrtal natively on a phone.

**Why this priority**: A major reach goal and the second client that justifies the client/core separation (Story 1) — but it follows the contract and core being in place.

**Independent Test**: From the mobile app, sign in, send a message to a model, and see the same live streaming/rendering the web client shows.

**Acceptance Scenarios**:

1. **Given** the mobile app, **When** the user sends a message, **Then** it streams and renders consistently with the other clients.

---

### User Story 16 - Operability: version identity and guaranteed runtimes (Priority: P4)

*[covers #6 (version numbers), #5 (Codex runtime in prod) → future operability work]*

Builds carry **clear version numbers** surfaced in `/status` and the internal representation, so dev and production are never visually confused. Provider/CLI **runtimes are guaranteed present** in each environment (no "runtime not found" at request time) — most cleanly via the sandbox images from Story 4, with a pre-deploy check that each provider's runtime actually starts.

**Why this priority**: Operational hygiene that makes everything else safe to test and ship; cheap, and partly subsumed by sandboxing.

**Independent Test**: Run `/status` on a dev and a production build and confirm distinct version identifiers; deploy and confirm each provider's runtime is present/startable before serving traffic.

**Acceptance Scenarios**:

1. **Given** a build, **When** `/status` is checked, **Then** it shows a version that distinguishes dev from production.
2. **Given** a deploy, **When** validated, **Then** each provider runtime is confirmed present/startable rather than failing at first request.

---

### Edge Cases (cross-cutting)

- A model/CLI **can't enforce Pawrrtal's tools** → its manifest says so (never silently degrade); the picker reflects the true enforcement level.
- A **CLI session created outside Pawrrtal** is adopted → best-effort per CLI; treated as a later, clearly-bounded slice, not a blocker.
- A **sandbox substrate is unavailable / over budget** → fall back to another substrate or a safe local default; never run untrusted code unsandboxed.
- **Removed systems** (permissions/budget/telemetry/workspaces) are referenced by old code → those paths are updated or deleted, not left dangling.
- **Secrets missing from Infisical** at run time → clear failure + safe fallback, never a plaintext fallback.
- A capability is needed by **only one client** (web/mobile) → it lives outside the core, behind the plugin/capability layer.
- **Migration in flight** → Python and Effect coexist behind stable contracts; no big-bang cutover; verification stays green throughout.
- **Files-first concurrency** → multiple channels (web / Telegram / Google Chat) appending to one conversation at once → appends to `messages.jsonl` are **`O_APPEND`-safe under a per-conversation advisory lock**, and `meta.json` mutations are **atomic temp+rename** (last-writer-wins).

## Requirements *(mandatory)*

> Grouped by area. Each group is the seed of a future split spec, which will expand these into detailed, testable requirements.

### Core, packaging & migration *(Stories 1–2, 6)*

- **FR-001**: The system MUST have a minimal core that depends on no optional capability; providers, channels, tools, transcription, browsing, projects, and settings MUST be separable packages/plugins.
- **FR-002**: The runtime MUST be a **thin core** (foundation · kernel · contract) plus **small uniform packages in clean namespace layers** — not a per-domain package zoo; capabilities MUST be added as **data, registry metadata, or a small uniform wrapper package (never by editing the kernel)**, per the 3-way rule (user → stored rows · team → declarative catalog · core → in-trunk module · external SDK → a wrapper package).
- **FR-003**: A new capability MUST be addable via the plugin/extension surface without modifying the core.
- **FR-004**: The backend MUST be migratable to TypeScript/Effect incrementally, with Python and Effect coexisting behind stable contracts during the transition (no big-bang cutover).
- **FR-005**: The CLI MUST be deliverable as a standalone Effect/TS package with parity to current verification flows (the migration pilot).
- **FR-006**: The permission system (and `permissions.md`), budget system, telemetry, and workspace system MUST be removed; logging MUST be retained.
- **FR-007**: The API surface MUST **auto-generate** its OpenAPI specification from the typed contract (no hand-written spec), serve interactive docs, and produce a **typed client** from the same contract; the contract is the single source of truth for the server, the docs, and every client.
- **FR-008**: Every frontend/client (web, mobile, CLI) MUST depend ONLY on the generated typed client of the contract — never importing backend runtime code; the contract is the only coupling. The contract MUST emit an **Effect-RPC surface, not only HTTP**, and the generated client's per-client configuration is **a configurable base URL + a profile/identity injector (`X-Pawrrtal-Profile` + optional bearer) + a transport selector** (WebSocket RPC to the tailnet backend; MessagePort RPC to a local runtime is deferred).
- **FR-009**: An **independently-buildable SDK boundary** (kernel + contracts + ports + `@clients/*` + the `paw` agent command group) MUST be able to **scaffold and run a standalone agent with NO Pawrrtal services** — no gateway, no profiles, no Tailscale, and no `$PAWRRTAL_DATA` layout (a local FileStore + one provider only). The **build MUST FAIL if the SDK (kernel/contracts/ports/clients) imports any app/runtime module** — the app→SDK dependency arrow is one-way and build-enforced. The SDK remains an **internal workspace-protocol, publishable-shaped** package set in v1; **npm publishing is deferred, not chosen** (see Constraints and Out of Scope).

### Gateway, providers & sessions *(Stories 3, 7–10)*

- **FR-010**: The system MUST expose one normalized way to drive any model or full agent CLI behind a stable contract, with the underlying mechanism (`-p`, SDK, local HTTP bridge, real API) swappable without observable change to callers.
- **FR-011**: The normalized contract MUST be a rich internal streamed parts model, exposed externally via an OpenAI/Anthropic-compatible API.
- **FR-012**: Each backed model MUST declare a truthful capability/enforcement manifest (tool enforcement level, streaming tier, session model); the picker MUST NOT over-promise capabilities the model cannot deliver.
- **FR-013**: Where a CLI supports it, Pawrrtal's own tools MUST be injectable through that CLI's tool seam; where it does not, the manifest MUST report tools as unenforced/unavailable.
- **FR-014**: Sessions MUST be trackable bidirectionally (Pawrrtal↔CLI), with exactly one context-owner-of-record per session so context cannot double or diverge.
- **FR-015**: Each model MUST appear once in the picker, with reasoning depth controlled by a separate effort knob (no per-effort duplicate entries).
- **FR-016**: Provider authentication (notably Antigravity/Google) MUST be reliable and configurable via a documented path; on failure it MUST fail clearly and fall back gracefully.
- **FR-017**: Active recall MUST operate through the provider abstraction for any selected model, and MUST produce nothing unless the user's message genuinely needs recalled information.

### Sandboxing & runtime *(Stories 4, 16)*

- **FR-020**: The agent MUST be able to provision an isolated sandbox on demand, run work or a full CLI inside it with live-streamed output, and tear it down.
- **FR-021**: The sandbox substrate MUST be pluggable with a **self-hosted / own-infra default**. The default tier MUST be a **local OS-confined tier** (`local-confined` — constrained CWD + network-off via OS primitives, **no container/microVM/image**). **microVM-class tiers** (Docker + gVisor, Kata, E2B) MUST be **opt-in**, selectable per conversation; any hosted/managed substrate (e.g. Upstash Box) is **opt-in only**.
- **FR-022**: Provider/CLI runtimes MUST be guaranteed present in each environment (no request-time "runtime not found"), with a pre-deploy check that each runtime starts.
- **FR-023**: A sandbox MUST be optionally bindable to a conversation (pause/resume/snapshot) so a session can be a resumable environment.

### Secrets *(Story 5)*

- **FR-030**: All secrets MUST be sourced through **self-hosted Infisical**; no secret may exist in plaintext in the repo or deployed config.
- **FR-031**: Every surface (app, CLI, CI, sandboxes) MUST obtain its secrets through Infisical at run time, including user-provided bot tokens.

### Surfaces, clients & onboarding *(Stories 11–13, 15)*

- **FR-040**: The system MUST let the agent/maintainer capture real rendered output and compare it against human-approved golden references across surfaces (detail in spec 002).
- **FR-041**: Supported surfaces MUST render rich media where the platform supports it.
- **FR-042**: Telegram MUST offer per-category verbosity toggles (independently show/hide tool calls, thinking, active-recall output, etc.) via inline controls.
- **FR-043**: A user MUST be able to bring their own Telegram bot (provide a token bound to their account) while the existing official-bot path keeps working.
- **FR-044**: Account creation and Telegram linking MUST be fully doable via API/CLI, with no web-app step required.
- **FR-045**: A mobile (React Native/Expo) client MUST consume the same backend contract and render the same streamed parts model as the other clients.
- **FR-046**: The backend MUST be exposed **privately over the tailnet** via `tailscale serve` (tailnet-only — **never** `funnel`), bound to `127.0.0.1` (loopback), replacing Cloudflare Access for the app/API. The backend MUST trust the spoof-proof **`Tailscale-User-Login`** header that `serve` injects (trustworthy because the backend is loopback-bound and `serve` strips any client-supplied copy). The **website** MAY stay same-origin; **native shells** (desktop, mobile) MUST reach the backend at a **runtime-configured tailnet base URL** (a `<node>.ts.net` host). A **public website is deferred** — no Cloudflared brochure/marketing path is required now. There MUST be **no token-issuing auth path, no session cookie, no CORS allowance for external origins, and no bearer-in-OS-secure-storage flow** as the identity mechanism (identity is profiles per FR-047).
- **FR-047**: Identity MUST be **profiles, not login**. The backend MUST list profiles (`GET /api/v1/profiles`); the user selects one. A profile MAY have an **optional per-profile password**; unlocking it (`POST /api/v1/profiles/{id}/unlock`) MUST return a **short-lived opaque bearer** used ONLY for password-locked profiles. Every request MUST carry **`X-Pawrrtal-Profile: <id>`** (plus `Authorization: Bearer <token>` only when the selected profile is locked). FastAPI-Users, the `session_token` cookie, `ALLOWED_EMAILS`, and the login/OAuth UI MUST be **retired**. On desktop the per-profile token MUST be held by the **Electron main process** and **never reach the renderer**.
- **FR-048**: The client MUST talk to the backend (and, post-v1, local processes) through **one Effect-RPC contract**. Transport MUST be a **swappable protocol layer**: for v1, **WebSocket** (`RpcClient.layerProtocolSocket` + `BrowserSocket.layerWebSocket`) to the tailnet backend; an Electron **MessagePort** path (`RpcClient.layerProtocolWorker` + `BrowserWorker.layer`) is **deferred** (local-first, post-v1). Streaming MUST use Effect `Stream` returns (ack-based backpressure + interrupt cancellation), **not** `ipcMain.invoke` (no streaming) or `webContents.send` (no backpressure). The hardened `contextBridge` (`contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, validated `senderFrame`, **never** exposing `ipcRenderer`) MUST remain the **security floor + handshake** (brokering the one-time MessagePort handoff for the deferred local path and privileged native ops) — **never the data path**.

### Capabilities & operability *(Stories 14, 16)*

- **FR-050**: A transcription service with pluggable backends (e.g. Fireflies) MUST transcribe at least voice notes and supported URLs (e.g. YouTube), as a plugin.
- **FR-051**: The system MUST support OpenClaw plugins and a browsing capability (Mirage) as plugins layered on the core.
- **FR-052**: Builds MUST carry a clear version identifier surfaced in `/status` and the internal representation, distinguishing dev from production.

## Key Entities *(include if feature involves data)*

- **Core**: the minimal, reliable agent runtime everything else layers onto.
- **Package / Plugin**: an independently-ownable unit of capability (provider, channel, tool, transcription backend, browsing, projects, settings) attached via the extension surface.
- **Normalized turn stream (message parts)**: the ordered, typed parts (text, reasoning, tool-call, tool-result, …) every model/CLI output is normalized to and every client renders.
- **Model / harness**: a selectable responder — a raw model (host runs the loop) or a full CLI harness (it owns the loop) — each with a capability/enforcement manifest.
- **Session record**: the mapping between a Pawrrtal conversation and a provider/CLI-native session, with a designated context-owner.
- **Profile**: the files-friendly identity substrate that **replaces account login** — a per-profile directory `profiles/<slug>/{profile.json, optional auth.json (password hash), preferences/personalization/appearance.json}`. The user selects a profile; an optional password unlock yields a short-lived opaque bearer for password-locked profiles.
- **Sandbox**: a disposable isolated environment with a **pluggable substrate**, default **`local-confined`** (constrained CWD + network-off, no container/microVM), with microVM-class tiers (Docker + gVisor, Kata, E2B) **opt-in**; the agent runs work/CLIs in it, optionally bound to a conversation.
- **ACP agent (sub-agent)**: an external coding agent (Gemini CLI / Claude Code / Codex) driven over the **Agent Client Protocol**, with host-enforced **`session/request_permission`** + `fs/*` + `terminal/*` callbacks against Pawrrtal's own workspace/sandbox — an **AgentProvider variant** (the successor to the hand-rolled CLI bridges).
- **Secret**: any credential, always resolved through Infisical, never stored in plaintext.
- **Golden reference**: a human-approved example of how a message kind should look on a surface.
- **Operator bot connection**: a user-provided or official bot bound to an account.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A non-core capability can be removed or swapped without editing the core and without breaking the core (verified for at least projects/settings and one provider); and the core (kernel) is consumed by **at least two independent in-repo apps through the generated contract only** (never importing kernel/runtime code directly), proving the SDK boundary holds in practice.
- **SC-002**: The CLI runs entirely on the Effect/TS package with 100% parity to current verification flows, while the rest of the system keeps working.
- **SC-003**: At least two different CLIs are usable through the gateway, each producing one normalized stream and a capability manifest that matches its real behavior.
- **SC-004**: Zero sessions desync — every resumed session has exactly one context-owner and never doubles/diverges context.
- **SC-005**: The agent can provision, use (with live output), and tear down a sandbox; and zero "runtime not found at request time" failures occur in production after the runtime-guarantee lands.
- **SC-006**: Zero plaintext secrets exist in the repo or deployed config; 100% of surfaces resolve secrets via Infisical.
- **SC-007**: The permission, budget, telemetry, and workspace systems are fully removed with logging intact and no dangling dependencies.
- **SC-008**: Each model appears exactly once in the picker with a working reasoning-effort knob.
- **SC-009**: A configured Antigravity/Google login succeeds, and credential failures produce a clear message + graceful fallback 100% of the time.
- **SC-010**: Active recall functions for any selected model and produces nothing on messages that don't require recalled information.
- **SC-011**: A user can be provisioned and chatting through their own bot using only the API/CLI, never opening the web app.
- **SC-012**: Per-category verbosity toggles independently control each category on Telegram; rich-media messages render on supported surfaces.
- **SC-013**: The mobile app streams and renders consistently with the web client for the same flow.
- **SC-014**: Transcription (voice note + URL), OpenClaw, and Mirage each work as installed plugins without core changes.
- **SC-015**: `/status` distinguishes dev from production via a version identifier.
- **SC-016**: In the end-state, **no Python remains** in the backend — the stack is entirely TypeScript / Effect (v4).
- **SC-017**: Adding a tool, provider, or channel is done by adding a discovered file/data with **zero edits to the kernel**; and the kernel is consumed by **2+ independent in-repo apps strictly through the generated contract** (no direct kernel/runtime imports), with the build **failing** if the SDK imports any app/runtime module.
- **SC-018**: The OpenAPI spec and the client SDK are **generated from the contract** (never hand-written) and stay in sync with it.
- **SC-019**: The app reaches the backend **only over the tailnet** (the public edge returns 403; `tailscale funnel status` is empty), authenticates by **profile selection** (no cookie / login), and streams agent output over **Effect-RPC with working cancellation**.
- **SC-020**: A `paw new`-scaffolded **two-file** project (`instructions.md` + `agent.ts`) runs via `paw run` over a local FileStore + one provider with **ZERO Pawrrtal services** (no gateway, profiles, Tailscale, or `$PAWRRTAL_DATA` layout).

## Constraints *(explicit, maintainer-chosen)*

These are deliberate decisions recorded as constraints (not implementation leakage):

- Target language/runtime: **TypeScript on Effect (v4 / effect-smol)** — **total** migration; no Python remains in the end-state. Effect v4 style references: **`../use-agy`** (maintainer-provided, exact v4 style), `comcom`, and vendored `backend/vendor/effect-smol`.
- **Deployment posture: default fully self-hosted** (Clarifications 2026-06-23) — managed services are used only where there is no practical self-hostable option; self-hosting MUST be possible end-to-end and no capability may hard-require a single managed cloud.
- Secrets manager: **self-hosted Infisical** (not Infisical Cloud).
- Sandbox substrate default: **`local-confined`** (constrained CWD + network-off via OS primitives like bubblewrap; **no container/microVM/image**). microVM-class drivers (**Docker + gVisor**, **Kata**, **E2B**) and any managed-cloud substrate (**Upstash Box**) are **opt-in, non-default** drivers behind the same `sandbox:runtime` slot. The core MUST NOT import a sandbox runtime — only the `SandboxRuntime` port and a tiny `local-confined` reference impl live near core; every heavyweight driver is a plugin package.
- Provider substrate to **build on, not reinvent**: the Effect AI layer (`@effect/ai`) / AI SDK patterns — but **no external AI Gateway as a default dependency**; Pawrrtal exposes its own gateway, and non-HTTP/CLI providers stay Pawrrtal-native.
- Mobile client: **React Native / Expo**.
- Decomposition: a **thin core** (`@platform/*` foundation + a one-loop `kernel` + the `api-core` contract) + **small uniform packages in clean namespace layers** — `@clients/*` (one per external SDK/provider/integration) and `@pawrrtal/*` product sub-domains; capabilities by the **3-way rule** (user→DB rows · team→declarative registry data · core→code module); partition by **code vs. data**, layer by **namespace**. comcom file conventions (`Domain·Api·Errors·RpcProtocol` contract / `Service·Repo·Policy·Http·Rpc` host; **no `index.ts` barrels**, `exports: "./*"`, `catalog:`/`workspace:*`). One contract → **HTTP + Effect RPC + auto-OpenAPI + generated client**.
- **Thin core is a publishable-*shaped* SDK boundary, built now — published later.** The thin core (kernel + `api-core` contract + ports + `@clients/*`) is an **internal workspace-protocol package set in v1**, shaped as if it were a standalone agent-building SDK, with a **build-enforced one-way app→SDK dependency arrow** (the app depends on the SDK; the SDK imports no app/runtime module). The publishable unit (internal in v1) = `kernel` + `api-core` + `@clients/*` + the `paw` **agent** command group; Pawrrtal is its first consumer. **Publishing to npm is DEFERRED, NOT CHOSEN** — mirroring the deferred website decision (recorded as a later effort, not a no) — and is gated on **all four** of: (1) the four shared contracts (`Part`/`PartDelta` fold, `ModelProvider`/`AgentProvider` + `CapabilityManifest`, `SessionRecord` single context-owner, the gateway internal envelope) **API-frozen for 2+ cycles**; (2) a **stable, non-`unstable`/non-beta Effect pin** (the `beta.74`-vs-`beta.85` reconciliation is a **publish blocker**; the internal boundary still picks one pin now); (3) **2+ in-repo consumers** driving the kernel through the **generated contract**; (4) an **external party actually asks**. The internal scope stays `pawrrtal` / `@pawrrtal/*`; a vendor-neutral `agentkit` scope is aliased **only at publish** (no public-name squatting now). `@clients/*` ship as a **curated starter subset at publish** (all live in `packages/clients/*` regardless); public package name + license are **decided at publish-time**.
- API: **OpenAPI auto-generated** from the typed `api-core` contract (no hand-written spec); Scalar docs; a **typed client** generated from the same contract.
- Frontends **fully decoupled**: the contract is the only coupling; web (Next), mobile (Expo), and the CLI consume the generated typed client and never import backend runtime code.
- Deployment: backend exposed **privately over the tailnet** via `tailscale serve` (tailnet-only — **never** `funnel`), bound to **loopback** (`127.0.0.1`); **Cloudflare Access is retired** for the app/API. A **public website is deferred** (not chosen — recorded as a later effort). **Identity = profiles** + the spoof-proof **`Tailscale-User-Login`** header (an optional short-lived per-profile bearer only for password-locked profiles). **Desktop = Electron** whose renderer uses **one Effect-RPC client over WebSocket** to the tailnet backend; the local bundled-runtime path (MessagePort to an Electron `utilityProcess`) is **deferred past v1**. The `contextBridge` stays **handshake + privileged-ops only**, never the data path. **Mobile = Expo** over the **same WebSocket RPC**. electron-updater + in-app update prompt retained. One frontend + one platform-detection facade (`frontend/lib/desktop.ts`); the contract/generated client stays the only data coupling.
- **Persistence: pure files, no database at all.** Conversations = per-conversation `meta.json` + append-only `messages.jsonl` (the `chat_messages` rows map 1:1 by `ordinal`); profiles, projects, memory, and config are plain files; the `.agent/` workspace tree stays as-is. All of it lives under a single **`$PAWRRTAL_DATA`** root (e.g. `~/.pawrrtal/`) that is a **git repo** for backups/history. In Effect this is a core-light **`FileStore`** service over effect-smol `FileSystem.ts` + `KeyValueStore.layerFileSystem(dir)`; ledgers/audit/cost become append-only JSONL logs too. **Search is ripgrep/scan over the JSONL** — there is **no SQLite index** (the slower-search-at-scale tradeoff is accepted). **No Postgres, no SQLite, no Alembic, no `@effect/sql`** for app data.

## Assumptions

- This is an **umbrella spec to be split** into per-feature specs before any `/speckit-plan`; it is not planned or implemented as a single unit.
- **Labor model**: the **maintainer-agent implements all stories** as small, parallel-**stacked** PRs, each independently gated (typecheck, `@effect/vitest`, harness, `paw verify`, sentrux). The per-split-spec decomposition is a **sequencing device, not an ownership boundary** — there are no separate per-feature owners or a contributor team.
- **Altitude is north-star end-state** — capabilities are described implementation-agnostically; mechanisms are decided per split spec at plan time.
- **Specs are migration-proof**: this document is intended to survive the Python→Effect migration and guide the rebuild, even where today's implementation is Python.
- **Audience is trusted-small-now**: success criteria target a handful of trusted users; tenants are assumed trusted (adversarial cross-tenant isolation deferred), and opening to untrusted/public multi-tenancy is an explicit later effort rather than designed-for today.
- Adoptions identified by prior research are treated as design inputs (not separate stories): the **message-parts data model**, **resumable streams**, **`@effect/ai` + optional gateway routing**, and **Eve-style conventions** (capability-as-file/package, skills-on-demand, channel-as-thin-adapter, durable sessions, sandboxed execution).
- A **test surface** (dedicated bot + chat) already exists for Story 11; provisioning it is out of scope.
- **`#24` (Vercel Chat SDK / Eve / AI SDK + Gateway)** is a design input feeding Stories 1–3, not its own story.

## Out of Scope (for this umbrella) / Split Plan

- This document does **not** define per-feature plans, tasks, data models, or contracts — those come after each story is split into its own spec and run through `/speckit-plan`.
- Intended split: **A** Story 11 *(=spec 002, done)* · **B** Story 8 · **C** Story 9 · **D** Story 10 · **E/I** Story 12 · **F** Story 13 · **J/N/R** Story 14 · **K** Story 1 · **L** Story 2 · **M** Story 5 · **Q** Story 15 · **S** Story 3 · **T** Story 4 · operability Story 16 · Claude provider Story 7 *(=spec 001, done)*.
- Story 7 (spec 001) and Story 11 (spec 002) are already split out as standalone specs.
- **No feature is deliberately excluded** from the overhaul (Clarifications 2026-06-23) — the 16 stories are the complete intended set; finer scope is bounded per split spec.
- **Publishing the kernel/SDK to npm, a public SDK docs site, and an independent SDK version cadence are DEFERRED, NOT CHOSEN** (mirroring the deferred-website decision) — the v1 SDK boundary is internal workspace-protocol packages with a build-enforced app→SDK arrow; the public publish is recorded as a later effort gated on the four conditions in Constraints (contracts frozen 2+ cycles, a stable non-beta Effect pin, 2+ in-repo consumers through the generated contract, and an external ask).

## Dependencies

- Many stories depend on **Story 1** (thin core + plugin system) and **Story 3** (gateway) being real; **Story 14** plugins ride on Story 1; **Story 13** bot tokens ride on **Story 5**; **Story 4** sandboxes underpin **Story 6**'s isolation-over-gating and **Story 16**'s runtime guarantee.
- The Python→Effect migration (**Story 2**) reshapes the substrate the other stories are ultimately built on; specs stay valid across it.
