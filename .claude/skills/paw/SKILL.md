---
name: paw
description: Pawrrtal Agent CLI. Use when you need to test the backend end-to-end as a real user — auth, workspaces, chat (with SSE streaming), conversation CRUD, provider verification. Prefer this over importing `app.*` modules in ad-hoc Python scripts; `paw` exercises the same HTTP surface the React frontend uses, so any bug visible in the UI is visible to `paw`.
paths:
  - "backend/**/*.py"
  - "frontend/features/chat/**/*"
  - "docs/superpowers/plans/*paw*"
  - "docs/design/codex*"
---

# paw — Pawrrtal Agent CLI

**Status:** Live. v1 commands shipped; v2 deferred per plan. See `docs/superpowers/plans/2026-05-27-agent-cli-user.md`.

When verifying claims like "the X provider works end-to-end" or "the chat roundtrip is intact," use `paw verify <suite>`. **Never** claim a behavior works based on a Python snippet that imports `app.*` directly — it bypasses auth, the FastAPI router, persistence, SSE framing, and the frontend's consumption shape. `paw` goes through the same HTTP API the React frontend calls, so any user-visible bug is `paw`-visible too.

## Quick start

```bash
just paw doctor                                # health-check the persona + backend
just paw login --dev-admin                     # seed the dev persona (cookie + workspace)
just paw verify codex --json                   # end-to-end Codex proof
just paw verify all --json                     # every shippable suite
```

`paw` lives at `backend/app/cli/paw/`. `just paw <args>` forwards to `cd backend && uv run paw <args>`.

## Resource map

Every row reflects a shipped subcommand. Source: `backend/app/cli/paw/commands/`.

| Resource         | Verbs                                                          | Endpoint family                          |
| ---------------- | -------------------------------------------------------------- | ---------------------------------------- |
| auth             | `login`, `logout`, `auth status`                               | `/auth/*`, `/api/v1/users/me`            |
| workspaces       | `ls`, `show`, `use`, `create`, `rename`, `delete`              | `/api/v1/workspaces`                     |
| workspace env    | `get`, `set`, `unset`                                          | `/api/v1/workspaces/{id}/env`            |
| workspace files  | `ls`, `cat`, `write`, `rm`                                     | `/api/v1/workspaces/{id}/files`          |
| channels         | `list`/`ls`, `link telegram`, `unlink telegram`                | `/api/v1/channels` + `/{provider}/link`  |
| mcp              | `list`/`ls`, `show`, `create`, `update`, `delete`              | `/api/v1/mcp/servers`                    |
| models           | `ls` (envelope: `{"models": [...], "etag": "..."}`)            | `/api/v1/models`                         |
| conversations    | `ls`, `show`, `create`, `send`, `rename`, `delete`, `export`   | `/api/v1/conversations`                  |
| messages         | `ls`, `get` (by `(conv_id, index)`; no `/messages/{id}` route) | `/api/v1/conversations/{id}/messages`    |
| api (raw)        | `METHOD PATH`, `openapi`, `ls`                                 | any                                      |
| record / replay  | `record COMMAND…`, `replay --from FILE`                        | local (respx-backed)                     |
| verify           | `codex`, `chat-roundtrip`, `model-switch`, `all`               | end-to-end                               |
| doctor           | (no verb)                                                      | local + ping `/api/v1/health` + models   |

## Conversation flow (important)

Conversations are addressed by **client-generated UUIDs**, same as the React frontend:

1. `paw conversations create` pre-generates a v4 UUID and `POST`s `/api/v1/conversations/{uuid}` with `{model_id, workspace_id, title}`.
2. `paw conversations send TEXT --conversation <uuid>` then `POST`s `/api/v1/chat/` with `conversation_id: <uuid>` (the field is **required** in `ChatRequest`, see `backend/app/schemas.py:301`).
3. `paw conversations send TEXT --new` is sugar for `create` + `send` with `--conversation`.

The chat stream is **custom SSE**: one JSON dict per `data:` line, terminated by the literal `data: [DONE]\n\n`. `paw` parses it the same way the frontend does (`fetch` + manual `\n\n` framing), so `paw` and the UI see the same bugs.

## Common workflows

### Verify a Codex provider change end-to-end

```bash
# After making a change to backend/app/core/providers/openai_codex/...
just paw verify codex --json | jq '.checks[] | select(.passed == false)'
```

8 sequenced HTTP calls + 17 named assertions (catalog → conversation creation → first turn streamed → conversation row + `codex_thread_id` persisted → messages stored → second turn → thread resumed → cleanup). Exits 0 if Codex works end-to-end. Exits 6 on any failed assertion; the JSON payload contains every emitted event + DB row state so the diagnosis is in the output.

### Verify chat-roundtrip against any model

```bash
just paw verify chat-roundtrip --model litellm:openai/gpt-4o-mini --json
```

Catalog → create conversation → send → assert non-empty `final_text` + persisted user/assistant rows → cleanup. Model-agnostic; default if `--model` omitted.

### Verify mid-conversation model switch

```bash
just paw verify model-switch --from litellm:openai/gpt-4o-mini --to litellm:anthropic/claude-3-5-sonnet --json
```

Create with model M1 → turn 1 → switch conversation to M2 → turn 2 → assert each turn ran against its assigned model.

### Verify everything shippable

```bash
just paw verify all --json
```

Runs `codex` + `chat-roundtrip` + `model-switch` in sequence; aggregate exit code is 6 if any single suite fails.

### Capture a fixture for unit tests, then replay offline

```bash
PAW_RECORD=backend/tests/paw/recordings/codex_hello.jsonl \
  just paw conv send "hello" --new --model openai-codex:openai/gpt-5.5

# Later, in a test or offline:
just paw replay --from backend/tests/paw/recordings/codex_hello.jsonl
```

### Run a custom request when no opinionated verb fits

```bash
just paw api POST /api/v1/conversations/01HZ.../title -d '{"title":"renamed"}'
just paw api openapi --json | jq '.paths | keys[]' | head
```

### Drive a multi-turn conversation

```bash
CONV=$(just paw conv create --model openai-codex:openai/gpt-5.5 --json | jq -r .id)
just paw conv send "First turn" --conversation "$CONV"
just paw conv send "Follow up" --conversation "$CONV"
just paw conv export "$CONV" --format md
```

## Output modes

Every command supports:

- (default) human text
- `--json` full machine-readable payload
- `--plain` TSV without headers, pipe-friendly for `awk` / `xargs`

`--json` mode **never** silently swallows errors: a failed command exits non-zero and emits `{"error": ..., "code": ..., "hint": ...}`.

## Exit codes

| Code | Meaning                        |
| ---- | ------------------------------ |
| `0`  | success                        |
| `1`  | local error (fs, parse)        |
| `2`  | missing argument / usage error |
| `3`  | auth (re-run `paw login`)      |
| `4`  | backend unreachable            |
| `5`  | API / provider error           |
| `6`  | verification failed            |

## Environment variables

| Var              | Purpose                                                          |
| ---------------- | ---------------------------------------------------------------- |
| `PAW_PROFILE`    | Persona profile (default: `default`)                             |
| `PAW_CONFIG_DIR` | Config root (default: `~/.config/pawrrtal`)                      |
| `PAW_RECORD`     | Capture HTTP + SSE traffic to this JSONL path                    |
| `PAW_E2E`        | `1` in pytest → run the live E2E suite (boots a real backend)    |

## Pitfalls

- **Never** assert "works end-to-end" based on `uv run python -c '... OpenAICodexProvider().stream() ...'`. That bypasses the chat router, auth, conversation persistence, SSE framing, and the frontend consumer pattern. Run `paw verify <suite>` instead.
- `GET /api/v1/models` returns an envelope `{"models": [...], "etag": "..."}`, not a bare list. `paw models ls` already handles this.
- `ChatRequest.conversation_id` is **required**. Always create the conversation first (the `--new` flag does this for you).
- `paw messages get` takes `(conversation_id, index)` since the backend exposes no `/messages/{id}` route — messages are indexed positionally within a conversation.
- `paw workspaces` now ships full CRUD (`create`/`rename`/`delete`), not just read verbs. Use it to script multi-workspace tests.
- The chat stream emits both provider-native `delta` events and a router-injected `message` event (`backend/app/api/chat.py:309`). `paw conv send` accumulates both into `final_text`.
- Cookies are stored at `~/.config/pawrrtal/<profile>/cookies.txt` (Mozilla format, mode `0600`). They include `Expires=...` headers with commas — `paw` uses a real cookie jar, never `.split(",")`.
- The Python SDK for Codex is pinned to `0.131.0a4` and the runtime to `openai-codex-cli-bin==0.131.0a4` (matched pair; upstream Python SDK hasn't moved past 0.131.0a4 even though CLI side reached 0.134.0).

## When to update this skill

- New `paw` subcommand → add it to the **Resource map**.
- New verify suite → add to **Common workflows**.
- New env var → add to **Environment variables**.
- New exit code → update the table.
- Behavior change that contradicts a "Pitfall" → fix the pitfall.

## See also

- `docs/superpowers/plans/2026-05-27-agent-cli-user.md` — implementation plan (v2).
- `backend/app/cli/paw/` — source.
- `backend/tests/paw/` — unit tests (104 mocked); `backend/tests/e2e_paw/` — live-backend gate (2 tests, `PAW_E2E=1`).
- `docs/design/codex-oauth-text-provider.md` — Codex provider doc; references `paw verify codex` as the canonical proof.
- `~/.claude/plugins/cache/claude-plugins-official/Notion/9847f2aa1a15/skills/notion/research-documentation/SKILL.md` — design inspiration (ntn).

## Status

v1 shipped (Tasks 0–11) on the `development` branch.

**Deferred to v2** (file as separate beans before implementing):

- `paw cost` — cost summary + ledger
- `paw audit` — audit events
- `paw jobs` — scheduled jobs
- `paw lcm` — LCM list/get + memories + dreaming
- `paw fanout N COMMAND...` — N parallel personas hitting the same backend
- `paw mirror --upstream URL COMMAND...` — local vs remote SSE diff
- `paw verify telegram-link-and-bot` — full channel E2E
- `paw verify cost-and-budget` — ledger + budget enforcement
- `paw verify lcm-active-recall` — Active Recall pre-turn agent integration
- `paw dev up/down/status` — process lifecycle for the dev launcher

**Open follow-up beans:**

- SQLite chat-path bug (live E2E currently green only against Postgres)
- Frontend migration off the `/users/me` compat alias to canonical `/api/v1/users/me`
