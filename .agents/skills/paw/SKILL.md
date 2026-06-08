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
just paw env check                             # check cache/config writability, binaries, ports
just env-check                                 # same check through repo-local writable dirs
just paw project up                            # start the full local app in the background
just paw project down                          # stop the CLI-launched full local app
just paw project service install               # install/start the user systemd dev service
just smoke-dev                                 # preflight + start + status + stop
just paw login --dev-admin                     # seed the dev persona (cookie + workspace)
just paw verify codex --json                   # end-to-end Codex proof
just paw verify all --json                     # every shippable suite
just paw lab flows ls --json                   # discover manual/live flow checklists
```

`paw` lives at `backend/app/cli/paw/`. `just paw <args>` forwards to `cd backend && uv run paw <args>`.
Run `scripts/paw --help` or `paw --help` after `just install-paw` when you need
the live command parser as the final source of truth.

## Resource map

Every row reflects a shipped subcommand. Source: `backend/app/cli/paw/commands/`.

| Resource         | Verbs                                                          | Endpoint family                          |
| ---------------- | -------------------------------------------------------------- | ---------------------------------------- |
| auth             | `login`, `logout`, `auth status`                               | `/auth/*`, `/api/v1/users/me`            |
| admin            | `seed-user`                                                    | local trusted operator path              |
| workspaces       | `ls`, `show`, `use`, `create`, `rename`, `delete`              | `/api/v1/workspaces`                     |
| workspace        | `status`, `skills`                                             | `/api/v1/workspaces/onboarding-status`, `/{id}/skills` |
| workspace env    | `get`, `set`, `unset`                                          | `/api/v1/workspaces/{id}/env`            |
| workspace files  | `ls`, `cat`, `write`, `rm`                                     | `/api/v1/workspaces/{id}/files`          |
| projects         | `ls`, `create`, `rename`, `delete`                             | `/api/v1/projects`                       |
| profile          | `get`, `set`                                                   | `/api/v1/personalization`                |
| appearance       | `get`, `set`, `reset`                                          | `/api/v1/appearance`                     |
| channels         | `list`/`ls`, `diagnose-telegram`, `link`, `unlink`, `send`     | `/api/v1/channels` + channel-specific routes |
| mcp              | `list`/`ls`, `show`, `create`, `update`, `delete`              | `/api/v1/mcp/servers`                    |
| plugins          | `scaffold`, `spec`, `validate`, `list`, `enable`, `disable`, `doctor`, `graph`, `reload`, `capabilities`, `slots` | dynamic plugin manifests and runtime snapshots |
| jobs             | `list`/`ls`, `show`, `create`, `delete`                        | `/api/v1/scheduled-jobs`                 |
| models           | `ls` (envelope: `{"models": [...], "etag": "..."}`)            | `/api/v1/models`                         |
| completions      | `autocomplete`                                                 | `/api/v1/completions/autocomplete`       |
| conversations    | `create`, `send`, `ls`, `show`, `rename`, `delete`, `export`   | `/api/v1/conversations`, `/api/v1/chat`  |
| messages         | `ls`, `get` (by `(conv_id, index)`; no `/messages/{id}` route) | `/api/v1/conversations/{id}/messages`    |
| cost             | `summary`, `ledger`                                            | `/api/v1/cost`, `/api/v1/cost/ledger`    |
| audit            | `ls`/`list`, `show`, `summary`                                 | `/api/v1/audit`                          |
| heartbeat        | `sync`                                                         | `/api/v1/heartbeat/sync`                 |
| lcm              | `context <conv-id>`                                            | `/api/v1/lcm/conversations/{id}/context` |
| api (raw)        | `request`, `openapi`, `ls`; root shorthand also accepts `METHOD PATH` | any authenticated backend route      |
| record / replay  | `record COMMAND…`, `replay --from FILE`                        | local fixture capture/replay             |
| fanout           | `<N> COMMAND…`                                                 | local orchestrator over N parallel personas |
| mirror           | `--upstream URL COMMAND…`                                      | local vs remote SSE diff                 |
| env              | `check`                                                        | local environment preflight              |
| project          | `up`, `down`, `status`, `preflight`, `logs`, `cloudflared ...`, `service ...`; root `run`/`stop` aliases | local full-stack lifecycle |
| verify           | `codex`, `chat-roundtrip`, `model-switch`, `telegram`, `google-chat`, `cost`, `lcm`, `all-providers`, `all` | end-to-end proof suites |
| lab              | `bench model/providers`, `runs ls/show/export/review`, `flows ls/show`, `telegram chat/media/providers` | exploratory benchmarks + dogfood |
| doctor           | (no verb)                                                      | local + ping `/api/v1/health` + models   |
| dev              | `up`, `down`, `status`                                         | local backend lifecycle (pid file at `<PAW_CONFIG_DIR>/<profile>/dev.json`) |

## Command groups at a glance

Top-level `paw` commands are: `run`, `stop`, `login`, `logout`, `record`,
`replay`, `fanout`, `mirror`, `doctor`, `dev`, `project`, `env`, `auth`,
`admin`, `projects`, `profile`, `appearance`, `conversations`, `workspaces`,
`workspace`, `channels`, `mcp`, `plugins`, `jobs`, `models`, `completions`,
`messages`, `cost`, `audit`, `heartbeat`, `lcm`, `lab`, `api`, and `verify`.

Use `paw api` when the backend route exists but the CLI does not have an
opinionated command yet. Use `paw plugins` for dynamic plugin manifests,
capability search, slot preference, and workspace runtime snapshots.

## Conversation flow (important)

Conversations are addressed by **client-generated UUIDs**, same as the React frontend:

1. `paw conversations create` pre-generates a v4 UUID and `POST`s `/api/v1/conversations/{uuid}` with `{model_id, workspace_id, title}`.
2. `paw conversations send TEXT --conversation <uuid>` then `POST`s `/api/v1/chat/` with `conversation_id: <uuid>` (the field is **required** in `ChatRequest`, see `backend/app/schemas.py:301`).
3. `paw conversations send TEXT --new` is sugar for `create` + `send` with `--conversation`.

The chat stream is **custom SSE**: one JSON dict per `data:` line, terminated by the literal `data: [DONE]\n\n`. `paw` parses it the same way the frontend does (`fetch` + manual `\n\n` framing), so `paw` and the UI see the same bugs.

## Common workflows

### Verify a Codex provider change end-to-end

```bash
# After making a change to backend/app/providers/openai_codex/...
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
just paw verify model-switch --from litellm:openai/gpt-4o-mini --to litellm:anthropic/Codex-3-5-sonnet --json
```

Create with model M1 → turn 1 → switch conversation to M2 → turn 2 → assert each turn ran against its assigned model.

### Verify the Telegram link-and-bot flow end-to-end

```bash
just paw verify telegram --json | jq '.checks[] | select(.passed == false)'
```

Lists channels → issues a one-time link code (asserts shape + future
expiry) → re-lists → unlinks → asserts the Telegram binding is gone.
For bot-side dogfood, enable `TELEGRAM_SIMULATE_ENABLED=true` on the
target backend, bind the persona's Telegram account once, then use
`paw lab telegram chat`.

### Verify the Google Chat channel

```bash
just paw verify google-chat --json | jq '.checks[] | select(.passed == false)'
```

Checks Google Chat formatting, command parsing, registration, and channel
runtime assumptions without relying on a generic chat smoke.

### Verify every available provider host

```bash
just paw verify all-providers --json | jq '.checks[] | select(.passed == false)'
```

Selects one authenticated model per allowed host (`google-ai`,
`gemini-cli`, `openai-codex`, `opencode-go` by default) and runs the
same chat-roundtrip scenario against each. Use `--host <host>` to narrow
the run and `--include-paid` when a live paid-model sweep is intentional.

### Benchmark providers and dogfood Telegram

```bash
just paw lab bench model --model google-ai:google/gemini-3.5-flash --prompt "hello" --runs 3 --json
just paw lab bench providers --runs 1 --json
just paw lab telegram chat --model google-ai:google/gemini-3.5-flash --turns /tmp/telegram-turns.txt --new --verbose 2 --json
just paw lab telegram media --model google-ai:google/gemini-3.5-flash --text "describe and transcribe" --image /tmp/sample.jpg --voice-note /tmp/sample.ogg --voice-duration 4 --new --json
just paw lab telegram providers --text "describe and transcribe" --image /tmp/sample.jpg --voice-note /tmp/sample.ogg --voice-duration 4 --verbose 2 --json
just paw lab runs ls --json
just paw lab runs review RUN_ID --question "What should feel cleaner before we ship this?"
just paw lab flows show backend-cli-coverage
just paw lab flows show telegram-polish-loop
```

Lab commands write profile-scoped JSON run logs under
`<PAW_CONFIG_DIR>/<profile>/lab/runs/`. `bench model` captures TTFT,
client duration, persisted backend duration, event counts, token usage,
thinking size, tool count, and final text size. `telegram chat` sends
scripted messages through `/api/v1/channels/telegram/simulate`, so the
visible Telegram conversation exercises the same dispatcher path as a
real inbound update without measuring raw CLI startup overhead.
`telegram media` sends one simulated Telegram media update with a JPEG
photo, a voice note, or both. Use it for end-to-end checks that image
interpretation and xAI voice transcription are happening before the
selected Paw agent model receives the turn.
`telegram providers` selects one authenticated model per provider host
from `/api/v1/models` and runs the same JPEG/voice-note media turn for
each host, producing one matrix run log with per-provider timing and
failure rows.
Use `lab runs review` to turn any stored run into the polish packet we
review together: prompt/control inputs, model, persisted transcript,
timing, media summary, run path, and the exact taste question.
Use `backend-cli-coverage` when checking whether a backend route family has
an opinionated Paw command, a verify suite, a lab flow, or an explicit raw
`paw api` fallback.
Use `telegram-polish-loop` when changing Telegram or tool rendering:
it names the taste checks to inspect before generalizing feedback into
`.agents/skills/pawrrtal-taste/SKILL.md`, `DESIGN.md`, or another flow.

### Verify cost ledger + budget enforcement

```bash
just paw verify cost --json | jq '.checks[] | select(.passed == false)'
```

Baselines `/api/v1/cost/` + `/api/v1/cost/ledger` → drives one chat
turn → asserts `current_usd` strictly increased and a new ledger row
references the new conversation with a non-zero `cost_usd`. The
per-user budget *limit* is configured via the
`cost_max_per_user_daily_usd` env setting (not a setter endpoint), so
the scenario emits a stable `budget_endpoint_unavailable` marker
check until a `POST /api/v1/cost/limit` route lands; the existing 402
enforcement path is exercised by `tests/api/test_chat_cost_budget.py`.

### Verify LCM observability after a chat

```bash
just paw verify lcm --json | jq '.checks[] | select(.passed == false)'
```

Resolves the default model -> creates a conversation -> streams two
chat turns -> asserts `GET /api/v1/lcm/conversations/{id}/context`
returns 200 with the expected envelope (`lcm_enabled`, `fresh_tail_count`,
`items`, `estimated_tokens`). When `lcm_enabled` is false in the env,
structural item-shape checks are skipped and a
`lcm_disabled_in_this_env` marker is emitted instead. The *full*
active-recall E2E (seed memories -> dream -> recall on a later turn) is
still blocked on `pawrrtal-x9u4`; the scenario emits stable
`memory_seeding_endpoint_unavailable` and
`dreaming_trigger_endpoint_unavailable` marker checks so the gap is
greppable until those endpoints land.

### Verify everything shippable

```bash
just paw verify all --json
```

Runs the configured proof suites in sequence, including provider/chat suites and
channel checks such as Telegram and Google Chat. Aggregate exit code is 6 if any
single suite fails.

### Work with dynamic plugins

```bash
just paw plugins scaffold demo-tool
just paw plugins spec --json
just paw plugins validate /path/to/plugin.json --json
just paw plugins list --workspace WORKSPACE_ID --json
just paw plugins enable PLUGIN_ID --workspace WORKSPACE_ID
just paw plugins doctor --workspace WORKSPACE_ID --json
just paw plugins capabilities search "notion" --workspace WORKSPACE_ID --json
just paw plugins slots --workspace WORKSPACE_ID --json
```

`paw plugins` is the operator surface for workspace CLI/plugin manifests:
schema inspection, manifest validation, enable/disable state, dependency graph,
snapshot reload, capability search, and slot preference.

### Run or stop the whole local project

```bash
just paw env check
just env-check
just paw project up
just paw project status --json
just paw project logs
just paw project down
just paw project service install
just paw project service status
just paw project service logs --follow
just paw project service uninstall

# Short aliases:
just paw run
just paw stop
```

`paw project up` launches the same root `dev.ts` orchestrator as `just dev`, but detaches it and stores state in `<PAW_CONFIG_DIR>/<profile>/project.json`. It writes combined output to `<PAW_CONFIG_DIR>/<profile>/project.log`, waits for both Next.js (`http://localhost:53001`) and FastAPI (`http://127.0.0.1:8000`) to respond, and `project down` stops the tracked process group. Use `paw dev up/down/status` only when you need the backend half by itself.

`paw project service install` writes a user systemd unit at `~/.config/systemd/user/pawrrtal-dev.service`, reloads systemd, and enables/starts it with `systemctl --user enable --now`. Use `--linger` when you want the user service to start at machine boot without an interactive login. Manage it with `paw project service start|stop|restart|status|logs|uninstall`.

`paw env check` and `paw project preflight` are non-interactive gates for agents. They fail before spawning if required binaries are missing, cache/config directories are not writable, dev ports are already occupied, or the current environment cannot bind local sockets. `just env-check` wraps the same check with repo-local writable state (`.cache/paw`, `.cache/uv`, `.cache/xdg`). `just smoke-dev` is the end-to-end startup gate: preflight, start, status, stop.

### Capture a fixture for unit tests, then replay offline

```bash
PAW_RECORD=backend/tests/paw/recordings/codex_hello.jsonl \
  just paw conversations send "hello" --new --model openai-codex:openai/gpt-5.5

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
CONV=$(just paw conversations create --model openai-codex:openai/gpt-5.5 --json | jq -r .id)
just paw conversations send "First turn" --conversation "$CONV"
just paw conversations send "Follow up" --conversation "$CONV"
just paw conversations export "$CONV" --format md
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
| `UV_CACHE_DIR`   | Set by `dev.ts` / `paw project up` to `.cache/uv` when unset     |
| `XDG_CACHE_HOME` | Set by `dev.ts` / `paw project up` to `.cache/xdg` when unset    |
| `PAWRRTAL_DEV_DATABASE_URL` | Explicit non-SQLite database URL for `dev.ts` / the user service |

## Pitfalls

- **Never** assert "works end-to-end" based on `uv run python -c '... OpenAICodexProvider().stream() ...'`. That bypasses the chat router, auth, conversation persistence, SSE framing, and the frontend consumer pattern. Run `paw verify <suite>` instead.
- `GET /api/v1/models` returns an envelope `{"models": [...], "etag": "..."}`, not a bare list. `paw models ls` already handles this.
- `ChatRequest.conversation_id` is **required**. Always create the conversation first (the `--new` flag does this for you).
- `paw messages get` takes `(conversation_id, index)` since the backend exposes no `/messages/{id}` route — messages are indexed positionally within a conversation.
- `paw workspaces` now ships full CRUD (`create`/`rename`/`delete`), not just read verbs. Use it to script multi-workspace tests.
- `paw project up` is the full app launcher; `paw dev up` is backend-only. If frontend is missing, you probably used the backend-only command.
- Run `paw env check` before debugging startup. It catches missing binaries, unwritable cache/config paths, occupied dev ports, and socket-bind denial before the stack emits nested tool traces.
- The chat stream emits both provider-native `delta` events and a router-injected `message` event (`backend/app/chat/router.py`). `paw conversations send` accumulates both into `final_text`.
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

## Status

Current `main` ships the broad CLI surface documented above: core resource
CRUD, local lifecycle, record/replay, fanout/mirror, dynamic plugins,
verification suites, and lab dogfood/benchmark flows. Treat `paw --help` and
`backend/app/cli/paw/` as authoritative when this skill and the parser disagree.

**Still blocked on backend work:**

- `paw lcm memories / lineages / dream` — blocked on backend HTTP surface (`pawrrtal-x9u4`). `paw lcm context` ships today.
- Full active-recall E2E (seeded memories surfacing after a dreaming pass) — depends on `pawrrtal-x9u4` so memories can be seeded and dreaming triggered programmatically. The observability slice (`paw verify lcm`) ships today and emits stable marker checks for both gaps.

**Known protocol drift to fix elsewhere:**

- `pawrrtal-95xr` — chat router doesn't catalog-validate `reasoning_effort` against the selected model before forwarding; surfaces as `UnsupportedParamsError` in `paw verify chat-roundtrip` when an incompatible (model, effort) pair is exercised.
