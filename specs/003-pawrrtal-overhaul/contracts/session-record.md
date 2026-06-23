# Contract 3 — Session Record + Context-Owner

**Purpose**: Generalize the existing provider-session persistence (`Conversation.provider_session_{kind,id,fingerprint}` + `ProviderSessionTurnState`, `provider_sessions.py`) into a **bidirectional Pawrrtal↔CLI mapping with exactly ONE declared context owner**, so the two sides never desync.

## SessionRecord (persisted per conversation)

| field | meaning |
|---|---|
| `pawrrtal_conversation_id` | Pawrrtal side of the mapping |
| `provider_kind` | which harness owns the native session (e.g. `openai_codex`, `agy_cli`); null if none |
| `provider_session_id` | opaque native handle (codex thread id, agy conversation id); null if none |
| `fingerprint` | `SHA256(model + workspace + system_prompt + tools)`; mismatch ⇒ abandon native session, start fresh |
| `context_owner` | **`pawrrtal | provider`** — WHO replays history. **EXACTLY ONE.** |

## SessionTurnState (prepared per turn)

Derived from `context_owner` (instead of each provider setting `omit_history` ad hoc):

- `context_owner = provider` ⇒ `omit_history = true` (Pawrrtal sends only the new turn; provider replays from its native session — agy_cli `provider.py:66`, codex when a thread exists).
- `context_owner = pawrrtal` ⇒ `omit_history = false` (Pawrrtal sends full history; provider is stateless for context).
- `stream_kwargs` — provider-native arg names forwarded ONLY to the preparing provider (`runner.py:233`); the host never inspects keys.

## Lifecycle

- **create**: provider emits the control signal `{ kind: provider_session_created, provider, session_id }` (codex `provider.py:347`, agy_cli `provider.py:137`); the runner persists it (`runner.py:281`).
- **resume**: `prepare_turn_session` loads the record → returns `SessionTurnState`; provider resumes its native thread.
- **invalidate**: fingerprint mismatch OR missing native rollout (codex `_is_missing_codex_rollout_error`) ⇒ clear handle, `context_owner` falls back to `pawrrtal`, replay full history.

## Invariant

**Never two context owners** (double-replays context) and **never zero** (drops context). Today this is implicit per-provider and subtly re-derived by each new harness; this contract makes it a single declared field validated at prepare time.

## Open

- Per-conversation **write-ownership lock** during the migration overlap (could both `:8000` and `:8001` write a conversation's turns?).
- Per-workspace credential injection for spawned-binary CLIs (today only logged, `openai_codex/provider.py:203`) and how it interacts with `context_owner`.
