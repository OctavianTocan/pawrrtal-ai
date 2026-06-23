# Data Model — Shared Entities (Pawrrtal Overhaul)

The cross-cutting entities every story shares. Detailed per-feature entities live in each split spec; these are the ones the contracts depend on. Implementation-agnostic (the Effect Schema.Class / SQL shapes are decided per slice, mirroring `backend-ts` Domain.ts patterns).

## Message & Part *(Contract 1)*

- **Message** — `{ id, conversation_id, role: user|assistant|tool, parts: Part[], status, usage?, created_at }`. `parts[]` is **order-significant, complete, lossless** (supersedes the lossy `chat_messages.timeline` JSON which only held thinking+tool). DB-resident and provider-agnostic — the source of truth for what every client renders.
- **Part** — discriminated union on `type`: `text` | `reasoning {text, block_index?, summary?}` | `tool_call {tool_call_id, name, input, display?}` | `tool_result {tool_call_id, output, is_error}` | `tool_progress {tool_call_id, output, transient}` | `error {message, error_code?}` | `artifact {kind, data, provider}` | `image {data, media_type}`.
- **Tool-call lifecycle** (on a `tool_call` part): `pending → running → completed | errored`; a `tool_result`/`tool_progress` patches its matching call by `tool_call_id`.
- **Usage** — message-level, **not** a part: `{ input_tokens, output_tokens, cost_usd, total_input_tokens?, total_output_tokens? }`.
- **PartDelta** (transport) — `{ op: append_part | patch_part | append_text, part_index?, tool_call_id?, value }`. Folding the full delta stream server-side and client-side MUST yield byte-identical `parts[]` (the live-vs-rehydrated invariant, made structural).

## Provider & CapabilityManifest *(Contract 2)*

- **Provider** — declares a **role** (exactly one): `ModelProvider` (host owns the loop) | `AgentProvider` (provider/CLI owns its loop).
- **CapabilityManifest** (declared, never inferred): `tool_enforcement: enforced | native-only | none`; `streaming_tier: incremental | turn-final`; `session_model: stateless | provider-session`; `reasoning: none | summary | raw`; `multimodal_in: bool`; `safety_honored: <subset of AgentSafetyConfig guards>`.

## SessionRecord *(Contract 3)*

- **SessionRecord** (persisted per conversation) — `{ pawrrtal_conversation_id, provider_kind?, provider_session_id?, fingerprint?, context_owner: pawrrtal | provider }`. `fingerprint = SHA256(model + workspace + system_prompt + tools)`; mismatch ⇒ abandon native session, start fresh, `context_owner` falls back to `pawrrtal`.
- **SessionTurnState** (per turn) — derived: `context_owner=provider ⇒ omit_history=true`; `context_owner=pawrrtal ⇒ omit_history=false`; plus `stream_kwargs` (provider-native, host never inspects). Invariant: **exactly one context owner** (never two = double-replay; never zero = dropped context). Generalizes today's `Conversation.provider_session_{kind,id,fingerprint}`.

## Package / Plugin / Slot *(Story 1 / Epic K)*

- **Package** — a capability that owns a contract (Protocol/HttpApi group), a **slot** name, its adapters, and its tests. Depends on `agent-core`, never on another package's internals.
- **Slot** — a named extension point on a package (`provider:models`, `channel:*`, `sandbox:runtime`, `stt:backend`, `conversation_memory`, …) drawn from the existing manifest capability taxonomy.
- **Plugin** — one concrete impl that fits exactly one slot; loaded by manifest (`plugin.json`); default-off unless intentionally enabled; never imports another plugin.
- **Core invariant** — `agent-core` MUST NOT import any provider SDK, concrete channel/transport, tool factory, plugin impl, secrets backend, sandbox runtime, or `settings`. Dependency DAG: plugins → packages → agent-core → contracts.

## Sandbox session *(Story 4 / Spec T)*

- **Sandbox** — `{ conversation_id, runtime: docker-gvisor | kata-microvm | e2b(opt-in), state: created|running|paused|destroyed, snapshot_ref? }`. One per conversation; exec output streams over the SSE parts contract; pause = stop+commit/snapshot keyed to `conversation_id`; resume = restart from snapshot. Default runtime = `docker-gvisor`; strict tier = `kata-microvm`.

## Secret *(Story 5 / Spec M)* — two planes, kept separate

- **Gateway/runtime plane** — infra secrets (`AUTH_SECRET`, `WORKSPACE_ENCRYPTION_KEY`, `DATABASE_URL`, shared fallback provider keys) resolved from **self-hosted Infisical** via process injection (`infisical run`, Machine Identity).
- **Workspace/user plane** — per-tenant provider keys & user bot tokens, held in Pawrrtal's **own encrypted workspace store** (`paw workspace env set`), NOT Infisical. Resolution port: `resolve(key, scope)`; **no plaintext anywhere; no plaintext fallback**.

## Persistence note

All of the above persist in the shared relational DB (Postgres prod / SQLite dev) whose schema is owned by **Alembic** during the migration; Effect reads via the generic `SqlClient` tag (driver swap = the only dev↔prod change). `parts[]` either backfills from or is synthesized on read from the legacy `{content, thinking, tool_calls, timeline}` columns (open question, resolved per slice).
