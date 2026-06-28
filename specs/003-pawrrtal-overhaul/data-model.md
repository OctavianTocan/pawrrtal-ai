# Data Model — Shared Entities (Pawrrtal Overhaul)

The cross-cutting entities every story shares. Detailed per-feature entities live in each split spec; these are the ones the contracts depend on. Implementation-agnostic (the Effect Schema.Class / SQL shapes are decided per slice, mirroring `backend-ts` Domain.ts patterns).

> **⚠️ SUPERSEDED — persistence note (2026-06-27).** The "Persistence note" section at the bottom of this file (the files-first `$PAWRRTAL_DATA`/`FileStore`/JSONL/ripgrep layout) is **superseded** by the ADR `frontend/content/docs/handbook/decisions/2026-06-27-rivet-postgres-electric-hatchet-substrate.mdx`. The **entities above are unchanged** (Message/Part, Provider/CapabilityManifest, SessionRecord, Package/Plugin/Slot, Sandbox, Secret) — they are substrate-agnostic. Only *where they live* changes: a **per-conversation Rivet actor** (running **Pi unforked**) owns the live transcript/turn state; **Postgres** is the API-written queryable record; **Electric** syncs it to devices; **Hatchet** runs system-level durable work. The `SessionStore`/`EventStreamStore` **ports survive** — see the updated persistence note below.

## Message & Part *(Contract 1)*

- **Message** — `{ id, conversation_id, role: user|assistant|tool, parts: Part[], status, usage?, created_at }`. `parts[]` is **order-significant, complete, lossless** (supersedes the lossy `chat_messages.timeline` JSON which only held thinking+tool). DB-resident and provider-agnostic — the source of truth for what every client renders.
- **Part** — discriminated union on `type`: `text` | `reasoning {text, block_index?, summary?}` | `tool_call {tool_call_id, name, input, display?}` | `tool_result {tool_call_id, output, is_error}` | `tool_progress {tool_call_id, output, transient}` | `error {message, error_code?}` | `artifact {kind, data, provider}` | `image {data, media_type}`.
- **Tool-call lifecycle** (on a `tool_call` part): `pending → running → completed | errored`; a `tool_result`/`tool_progress` patches its matching call by `tool_call_id`.
- **Usage** — message-level, **not** a part: `{ input_tokens, output_tokens, cost_usd, total_input_tokens?, total_output_tokens? }`.
- **PartDelta** (transport) — `{ op: append_part | patch_part | append_text, part_index?, tool_call_id?, value }`. Folding the full delta stream server-side and client-side MUST yield byte-identical `parts[]` (the live-vs-rehydrated invariant, made structural).

## Provider & CapabilityManifest *(Contract 2)*

- **Provider** — declares a **role** (exactly one): `ModelProvider` (host owns the loop) | `AgentProvider` (provider/CLI owns its loop).
- **CapabilityManifest** (declared, never inferred): `tool_enforcement: enforced | native-only | none`; `streaming_tier: incremental | turn-final`; `session_model: stateless | provider-session`; `reasoning: none | summary | raw`; `multimodal_in: bool`; `safety_honored: <subset of AgentSafetyConfig guards>`.
- **ACP** is the AgentProvider that declares `tool_enforcement: enforced` (not `native-only`) because the host implements ACP's `session/request_permission` + `fs/*` + `terminal/*` callbacks against Pawrrtal's own workspace/sandbox — distinguishing it from `codex` (`native-only`) and `agy_cli` (`none`).

## SessionRecord *(Contract 3)*

- **SessionRecord** (persisted per conversation) — `{ pawrrtal_conversation_id, provider_kind?, provider_session_id?, fingerprint?, context_owner: pawrrtal | provider }`. `fingerprint = SHA256(model + workspace + system_prompt + tools)`; mismatch ⇒ abandon native session, start fresh, `context_owner` falls back to `pawrrtal`.
- **SessionTurnState** (per turn) — derived: `context_owner=provider ⇒ omit_history=true`; `context_owner=pawrrtal ⇒ omit_history=false`; plus `stream_kwargs` (provider-native, host never inspects). Invariant: **exactly one context owner** (never two = double-replay; never zero = dropped context). Generalizes today's `Conversation.provider_session_{kind,id,fingerprint}`.

## Package / Plugin / Slot *(Story 1 / Epic K)*

- **Package** — a capability that owns a contract (Protocol/HttpApi group), a **slot** name, its adapters, and its tests. Depends on `agent-core`, never on another package's internals.
- **Slot** — a named extension point on a package (`provider:models`, `channel:*`, `sandbox:runtime`, `stt:backend`, `conversation_memory`, …) drawn from the existing manifest capability taxonomy.
- **Plugin** — one concrete impl that fits exactly one slot; loaded by manifest (`plugin.json`); default-off unless intentionally enabled; never imports another plugin.
- **Publishable SDK boundary** — the `kernel` (turn loop + compaction + the ports as interfaces), the **four shared contracts** (`Part`/`PartDelta`; `Provider`/`CapabilityManifest`; `SessionRecord`; the gateway internal parts envelope), and the **ports** (Provider, ToolRegistry + permission-check, Channel, SandboxRuntime, FileStore/SessionStore, Secret, Memory, Observability) together form the **publishable SDK boundary** — built now as internal workspace-protocol packages, with the npm publish deferred (not chosen) behind its gates. The dependency arrow is **build-enforced one-way: app depends on SDK, never the reverse**; `apps/api` (host: profiles, Tailscale, `$PAWRRTAL_DATA`, façade, channels) imports the SDK packages, and nothing in the SDK reaches back into the host. The `@clients/*` wrappers depend **only on the `@platform/*` foundation** (and the contract types), never on `apps/api` or any concrete port impl.
- **Core invariant** — `agent-core`/`kernel` wraps the **Pi harness** (`@earendil-works/pi-agent-core`, unforked) as its one sanctioned upstream dependency, but otherwise MUST NOT import any provider SDK, concrete channel/transport, tool factory, plugin impl, secrets backend, sandbox runtime, or `settings` — and, more strongly, **MUST NOT import any app/runtime module at all** (no `apps/api` host code, no `$PAWRRTAL_DATA` layout, no profile/Tailscale/façade code): the SDK→app direction is forbidden, not just the SDK→concrete-impl direction. Dependency DAG: plugins → packages → agent-core (→ Pi) → contracts; and app → SDK (one-way).

## Sandbox session *(Story 4 / Spec T)*

- **Sandbox** — `{ conversation_id, runtime: local-confined | docker-gvisor | kata-microvm | e2b(opt-in) | gondolin-microvm(opt-in, self-hosted) | upstash-box(opt-in), state: created|running|paused|destroyed, snapshot_ref? }`. One per conversation; exec output streams over the SSE parts contract; **pause/resume is provider-agnostic and best-effort** — live memory+FS snapshot where the driver supports it (e2b), else **disk-checkpoint + cold resume** (gondolin's qcow2 checkpoint, `local-confined` rehydrate-from-git) — keyed to `conversation_id`. Default runtime = `local-confined` (CWD-confinement + network-off via OS primitives — bubblewrap — no Docker/KVM/image). Opt-in tiers: `docker-gvisor`, `kata-microvm`, `e2b`, **`gondolin-microvm`** (self-hosted Alpine micro-VM — QEMU/krun, programmable egress + secret injection; needs QEMU/KVM + Node ≥23, so opt-in only); `upstash-box` opt-in only (managed-cloud). **Core invariant**: only the `SandboxRuntime` port + the `LocalConfinedRuntime` reference impl live near core; every heavyweight driver is a plugin.

## Secret *(Story 5 / Spec M)* — two planes, kept separate

- **Gateway/runtime plane** — infra secrets (`AUTH_SECRET`, `WORKSPACE_ENCRYPTION_KEY`, `DATABASE_URL`, shared fallback provider keys) resolved from **self-hosted Infisical** via process injection (`infisical run`, Machine Identity).
- **Workspace/user plane** — per-tenant provider keys & user bot tokens, held in Pawrrtal's **own encrypted workspace store** (`paw workspace env set`), NOT Infisical. Resolution port: `resolve(key, scope)`; **no plaintext anywhere; no plaintext fallback**.

## Persistence note

> *(⚠️ SUPERSEDED 2026-06-27 — see top banner. The files-first text in this section is retained for history; the substrate ADR is the source of truth.)*

**New substrate.** Live session state (the transcript + turn/queue/per-session-cron state) lives in a **per-conversation Rivet actor** running **Pi unforked**, persisted to that actor's on-disk SQLite and streamed over its WebSocket. The **cross-cutting record** (conversation list/metadata, profiles, projects, automations, integrations, settings, search) lives in **Postgres**, with the **API as sole writer**; **Electric** syncs those read-models to every device through an identity-scoped gatekeeper proxy. **Hatchet** runs system-level durable work (global crons, automations, inbound integrations) and reaches conversations only by messaging their actors. **Single-writer-per-store** is the load-bearing invariant: actor owns its session, API owns Postgres, actor↔API over RPC. Search depth (metadata-only vs a projected message-text digest vs a full mirror) is **consciously deferred** to the validating spike.

~~All of the above persist as **pure files — there is no database at all** (no Postgres, no SQLite, no Alembic for app data; no `@effect/sql` for app data). Everything lives under a single `$PAWRRTAL_DATA` root (e.g. `~/.pawrrtal/`) that is itself a **git repo** for backups/history. In Effect this is a core-light **`FileStore`** service over effect-smol `FileSystem.ts` + `KeyValueStore.layerFileSystem(dir)`.~~

Layout (by entity):

- **Conversations** — one directory per conversation holding a `meta.json` (id, title, provider/session fields, timestamps) plus an append-only `messages.jsonl`. Each `chat_messages` row maps **1:1 by `ordinal`** to one JSONL line; the file is the ordered source of truth for what every client renders.
- **Profiles** — `profiles/<slug>/{profile.json, auth.json?, preferences/personalization/appearance.json}`. `auth.json` is present only when the profile has a password (holds the password hash); `preferences/personalization/appearance.json` carry per-profile settings.
- **Projects** — `project.json` per project.
- **Memory** — an append-only `memory.jsonl`.
- **`.agent/` workspace tree** — unchanged; persists as-is alongside the above.

**Search** is ripgrep/scan over the JSONL (no SQLite index; the slower-search-at-scale tradeoff is accepted). **Alembic no longer owns app data** — schema now lives in the JSON/JSONL readers, and a one-shot exporter writes the file tree (from any legacy relational data). `parts[]` either backfills from or is synthesized on read from each `messages.jsonl` row's legacy `{content, thinking, tool_calls, timeline}` fields (open question, resolved per slice).

**Persistence port vs. layout (unchanged seam, new realization).** The persistence **port** is still a substrate-agnostic `SessionStore` / `EventStreamStore` — an **SDK interface** (a `Context.Tag` service), the boundary the kernel folds parts and replays turns against. It is **distinct from** its concrete realization. Under the superseded model that realization was the `$PAWRRTAL_DATA` files layout; under the substrate ADR it is the **per-conversation Rivet actor's on-disk SQLite** (live transcript/turn state, the kernel's fold/replay target) plus a **Postgres projection written by the API** (the cross-cutting, Electric-synced record). The SDK still owns the port and the fold/replay helpers; `apps/api` owns the actor + Postgres realization. Swapping the substrate replaces only the app-side impl, never the kernel — exactly the property this seam exists to guarantee. *(The SDK's standalone reference impl remains a simple local store, so a `paw new` project still runs with no actor/Postgres/Electric.)*
