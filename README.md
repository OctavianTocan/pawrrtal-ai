# ![logo](assets/pawrrtal-icon.png "logo") Pawrrtal

<p align="center">
  <a href="docs/assets/header.mp4" title="Click for the full-resolution MP4">
    <img src="docs/assets/header.gif" alt="Pawrrtal demo" width="100%" />
  </a>
</p>

[![Formatted with Biome](https://img.shields.io/badge/Formatted_with-Biome-60a5fa?style=flat&logo=biome)](https://biomejs.dev/)
[![Linted with Biome](https://img.shields.io/badge/Linted_with-Biome-60a5fa?style=flat&logo=biome)](https://biomejs.dev)
[![Sentrux](https://img.shields.io/badge/Architecture-Sentrux-7c3aed?style=flat)](https://github.com/sentrux/sentrux)

**Pawrrtal** is a personal AI assistant — a "Paw" of your own — that runs across the web, your desktop, and Telegram. Every user gets their own **workspace**: a filesystem-backed sandbox with its own memory, skills, and encrypted credentials. The agent reads and writes through a hardened workspace jail, calls a curated set of tools, and reasons against your own context (SOUL.md, AGENTS.md, skills) rather than a one-size-fits-all system prompt.

> **Pawrrtal vs an "AI chatbot"**: Pawrrtal is not just a Gemini wrapper. It runs a provider-agnostic agent loop (Claude, Gemini, …) over a stable `AgentTool` contract, with per-workspace API keys, a plugin system for first-party integrations, a Telegram bot that's a peer of the web client, and an electron/electrobun desktop shell — all backed by the same FastAPI core.

---

## Features

### Agent
- **Multi-provider** — Anthropic Claude (via `claude-agent-sdk`) and Google Gemini (via `google-genai`) behind one `AILLM` protocol. Catalog-driven model selection; per-conversation override.
- **Provider-agnostic tool layer** — `AgentTool` shape compiled separately into Claude's in-process MCP server and Gemini's `FunctionDeclaration`. Tools never live inside provider files (enforced by `scripts/check-no-tools-in-providers.py`).
- **Streaming everywhere** — Server-Sent Events on web/electron; progressive message edits on Telegram. Same `StreamEvent` shape end-to-end.
- **Safety limits** — per-turn iteration cap, wall-clock budget, consecutive-error budgets, exponential retry; all tunable via env.
- **Cost ledger + budget gate** — token + USD per turn persisted to `cost_ledger`; per-request and per-user rolling-window caps enforced at the chat endpoint (HTTP 402 on overage).

### Channels & surfaces
- **Web** — Next.js 16 / React 19 chat with chain-of-thought, tool-call timeline, artifact rendering (`json-render`), file attachments, model picker.
- **Telegram** — aiogram-backed bot. Link-code binding (`/start <code>`), `/new`, `/model`, `/models` (inline keyboard), `/verbose 0|1|2`, `/stop`, `/status`. Live tool-trace UI (thinking + tool calls + final answer as separate messages, all `reply_to` the user's turn).
- **Electron + Electrobun** — desktop shells; all desktop-only IPC goes through `frontend/lib/desktop.ts` with web fallbacks so the frontend stays portable.

### Workspaces
- One default workspace per user; secondary workspaces are first-class.
- Backed by a real directory (`{base}/{workspace_id}/`) containing `SOUL.md`, `AGENTS.md`, `BOOTSTRAP.md`, `memory/`, `skills/`, `artifacts/`, and a Fernet-encrypted `.env`.
- System prompt is **assembled per-turn** from the workspace (`PAW_CORE` + SOUL + AGENTS + BOOTSTRAP + skills index).
- The Claude SDK runs with `setting_sources=[]` and `cwd=<workspace_root>`, so it can't read the host repo's `CLAUDE.md`, hooks, or `.mcp.json`.

### Tools
| Tool | Gating |
|---|---|
| `read_file` / `write_file` / `list_dir` (workspace jail with `O_NOFOLLOW`) | always |
| `exa_search` (web search) | `EXA_API_KEY` |
| `image_gen` (PNG into workspace) | `OPENAI_CODEX_OAUTH_TOKEN` |
| `markitdown_convert` (PDF/Word/…→ Markdown) | always |
| `send_message` (channel-agnostic mid-turn push) | when surface supplies a `send_fn` |
| `send_image_to_user` / `send_voice_to_user` / `send_document_to_user` | Telegram surface only |
| `python` (in-process `exec()`, workspace-jailed `fs`) | `virtual_python_enabled` (off by default) |
| `render_artifact` (structural client-side render) | always |
| `lcm_grep` / `lcm_describe` / `lcm_list_summaries` / `lcm_expand_query` | `lcm_enabled` + conversation id |

### Plugin system
- Plugins declare env keys + tool factories under `backend/app/integrations/<id>/plugin.py` and call `register_plugin(...)`.
- `build_agent_tools` appends plugin tools after the core set when activation predicates resolve (default: every declared env key is present for the workspace).
- **Notion plugin** (18 tools) is the first consumer: `notion_search`, `notion_read`, `notion_create`, `notion_update_markdown`, `notion_query`, `notion_sync`, `notion_logs_read`, …
  - Per-call subprocess of the official `ntn` CLI with `NOTION_API_TOKEN` injected and `HOME` set to a per-call tempdir.
  - Every call is audited in `notion_operation_logs` (indexed on workspace, tool, page/database, created_at).

### Lossless Context Management (LCM)
DAG-based conversation compaction. As conversations grow past `lcm_context_threshold` of the model window, older turns are summarised into queryable `LCMSummary` nodes while the fresh tail stays verbatim. Four agent tools (`lcm_grep`, `lcm_describe`, `lcm_list_summaries`, `lcm_expand_query`) let the agent search, enumerate, inspect, and synthesise across compacted history. Off by default (`lcm_enabled=false`).

### Observability
- OpenTelemetry traces on `pawrrtal.turn` and `pawrrtal.llm.chat` spans (TTFT, duration, token counts).
- OpenLLMetry / Raindrop Workshop integration via OTLP — same global TracerProvider.
- Every audit-worthy event lands in `audit_events`; security risk levels auto-computed.

---

## Tech stack

| Layer       | Stack |
|-------------|-------|
| Frontend    | Next.js 16, React 19, Tailwind v4, TanStack Query, Fumadocs |
| Backend     | FastAPI, Python 3.13, SQLAlchemy 2 async, Alembic, fastapi-users |
| Database    | PostgreSQL (prod, Railway), SQLite + aiosqlite (tests / fresh dev) |
| Providers   | `claude-agent-sdk` (Anthropic), `google-genai` (Gemini) |
| Channels    | aiogram (Telegram, polling or webhook), SSE (web/electron) |
| Encryption  | Fernet (workspace `.env`) |
| Desktop     | Electron, Electrobun (Bun + system webview) |
| Toolchain   | Bun, uv, Biome, Ruff, mypy strict, Bandit, just, Lefthook |
| Arch gates  | Sentrux, import-linter (backend), dependency-cruiser (frontend) |

---

## Quick start

### Prerequisites
- [Bun](https://bun.sh) (frontend runtime + package manager)
- [uv](https://docs.astral.sh/uv/) (Python package + venv manager)
- Python 3.13+
- Postgres 16 (prod-like dev) **or** nothing extra (SQLite for tests)
- At least one of: `GOOGLE_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`

### Install
```bash
git clone --recurse-submodules https://github.com/OctavianTocan/Pawrrtal-AI.git pawrrtal
cd pawrrtal

# Vendored submodules (react-overlay, react-dropdown, react-chat-composer)
# If you forgot --recurse-submodules:
git submodule update --init --recursive

just install      # bun install + uv sync
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# Fill in AUTH_SECRET, WORKSPACE_ENCRYPTION_KEY, at least one provider key.
```

### Run dev
```bash
just dev          # Next.js on :3001, FastAPI on :8000
# or
bun run dev       # same thing — wraps dev.ts
```

The orchestrator (`dev.ts`) clears stale ports, removes the Next.js dev lock, and launches both servers with hot reload. Plain `localhost` (no HTTPS / proxy / fake hostnames).

### Docker
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```
Postgres on `:5432`, backend on `:8000`. The prod overlay (`docker-compose.prod.yml`) adds the Next.js service and an nginx reverse proxy on `:80`.

### Logs
Backend writes a rotated combined log to `backend/app.log`:
```bash
tail -f backend/app.log
```

---

## Configuration

Settings live in `backend/app/core/config.py` (pydantic-settings). Highlights:

```bash
# Auth
AUTH_SECRET=                # JWT signing key (required)
ALLOWED_EMAILS=             # CSV allowlist; empty = open

# Database
DATABASE_URL=postgresql+psycopg://...   # or sqlite+aiosqlite:///./app.db

# Workspace
WORKSPACE_BASE_DIR=/data/workspaces
WORKSPACE_ENCRYPTION_KEY=   # base64-encoded 32-byte Fernet key

# Providers (gateway fallbacks; per-workspace overrides win)
GOOGLE_API_KEY=
CLAUDE_CODE_OAUTH_TOKEN=
EXA_API_KEY=
XAI_API_KEY=
OPENAI_CODEX_OAUTH_TOKEN=
NOTION_API_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_MODE=polling                  # or webhook
TELEGRAM_WEBHOOK_URL=
TELEGRAM_VERBOSE_DEFAULT=1             # 0=quiet, 1=tools, 2=thinking

# Safety
AGENT_MAX_ITERATIONS=25
AGENT_MAX_WALL_CLOCK_SECONDS=300
AGENT_MAX_CONSECUTIVE_LLM_ERRORS=3
AGENT_MAX_CONSECUTIVE_TOOL_ERRORS=5

# Cost
COST_TRACKER_ENABLED=true
COST_MAX_PER_REQUEST_USD=1.0
COST_MAX_PER_USER_DAILY_USD=10.0

# LCM (lossless context management)
LCM_ENABLED=false
LCM_FRESH_TAIL_COUNT=64
LCM_LEAF_CHUNK_TOKENS=20000
LCM_CONTEXT_THRESHOLD=0.75
LCM_SUMMARY_MODEL=

# Python tool (UNSANDBOXED — single-tenant only)
VIRTUAL_PYTHON_ENABLED=false

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=
OTEL_SERVICE_NAME=pawrrtal-backend
```

### Per-workspace API keys
Six keys are overridable per workspace (file: `{base}/{workspace_id}/.env`, Fernet-encrypted, `chmod 0o600`):
`GEMINI_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `EXA_API_KEY`, `XAI_API_KEY`, `OPENAI_CODEX_OAUTH_TOKEN`, `NOTION_API_KEY`.
Frontend exposes them via **Settings → Environment**. Empty values fall back to the gateway global.

---

## Architecture

### Request → response (web chat turn)

```
Browser ─SSE─▶ Next.js (:3001) ─fetch─▶ FastAPI /api/v1/chat
                                              │
                       ┌──────────────────────┼──────────────────────┐
                       ▼                      ▼                      ▼
              _require_workspace       resolve_llm()        build_agent_tools()
              (412 if missing)        (workspace_id +       (workspace tools,
                                       workspace_root)       exa, image-gen,
                                                             markitdown,
                                                             plugins…)
                                              │
                                              ▼
                                  Channel.deliver(
                                      provider.stream(...)
                                        └─ agent_loop(...)
                                             └─ StreamFn ────────────┐
                                                                     │
                                                          Claude SDK / Gemini API
```

- `chat.py` resolves workspace → cost gate → provider → tools → channel.
- `provider.stream(...)` calls `agent_loop()` with a per-request `StreamFn` (the only seam tests inject `ScriptedStreamFn` at).
- `agent_loop` runs the LLM → tool dispatch → LLM loop, enforces safety budgets, and emits `AgentEvent`s.
- The provider translates `AgentEvent → StreamEvent` and yields back.
- `Channel.deliver` is web (SSE frames) or Telegram (progressive edits + final reply).

### Repo layout

```
pawrrtal/
├─ backend/
│  ├─ main.py                       # FastAPI app composition + lifespan
│  ├─ app/
│  │  ├─ api/                       # Routers (chat, conversations, models,
│  │  │                             #         workspace, workspace_env, channels,
│  │  │                             #         cost, audit, stt, oauth, projects, …)
│  │  ├─ channels/                  # Channel protocol, turn_runner, sse, telegram_*
│  │  ├─ core/
│  │  │  ├─ agent_loop/             # Provider-neutral loop, types, safety
│  │  │  ├─ agent_tools.py          # Per-turn tool composition
│  │  │  ├─ plugins/                # Plugin registry + types
│  │  │  ├─ providers/              # ClaudeLLM, GeminiLLM, catalog, model_id, bridges
│  │  │  └─ tools/                  # Concrete tool implementations
│  │  ├─ crud/                      # SQLAlchemy CRUD per domain
│  │  ├─ integrations/
│  │  │  ├─ notion/                 # 18-tool plugin via `ntn` subprocess
│  │  │  ├─ telegram/               # aiogram bot, handlers, status, model picker
│  │  │  ├─ voice/                  # Mistral / OpenAI / Whisper.cpp transcribers
│  │  │  └─ webhooks/               # Inbound webhook receivers
│  │  ├─ governance_models.py       # audit_events, cost_ledger, scheduled_jobs, …
│  │  ├─ models.py                  # User, Conversation, Message, Workspace, LCM, …
│  │  └─ schemas.py                 # Pydantic API schemas
│  ├─ alembic/                      # Migrations (single-head; advisory-lock on prod boot)
│  ├─ Dockerfile
│  └─ railway.toml
├─ frontend/
│  ├─ app/                          # Next.js App Router
│  │  ├─ (app)/                     #   shell + chat + dashboard + knowledge + tasks
│  │  ├─ (auth)/                    #   login / signup
│  │  ├─ settings/                  #   settings sections
│  │  └─ api/                       #   Next.js route handlers (proxy + search)
│  ├─ features/                     # chat, nav-chats, channels, onboarding,
│  │                                # auth, settings, projects, knowledge, …
│  ├─ components/                   # ai-elements, brand-icons, ui (shadcn primitives)
│  ├─ hooks/                        # useAuthedFetch, useAuthedQuery, …
│  ├─ lib/                          # api.ts, desktop.ts, types.ts, ai-utils, …
│  └─ content/docs/handbook/        # In-app handbook (Fumadocs)
├─ electron/                        # Desktop shell (main / preload / ipc)
├─ electrobun/                      # Bun + system webview shell (smaller)
├─ docs/                            # Plans, ADRs, deployment guides, hyperframes/
├─ scripts/                         # check-file-lines, check-nesting, install-runner, …
├─ docker-compose.{yml,dev,prod,demo}.yml
├─ nginx/                           # Reverse proxy config (prod compose)
├─ justfile
├─ DESIGN.md                        # Design tokens (canonical values in globals.css)
├─ AGENTS.md / CLAUDE.md            # Repo conventions (CLAUDE.md is a symlink)
└─ CHANGELOG.md
```

---

## Channels & surfaces

| Surface  | Inbound                                 | Outbound                              |
|----------|------------------------------------------|----------------------------------------|
| Web      | `POST /api/v1/chat` (header `X-Pawrrtal-Surface: web`) | SSE frames `data: <json>` + `[DONE]` |
| Electron | Same SSE endpoint, surface `electron`    | Same                                   |
| Telegram | Polling or webhook → aiogram dispatcher  | Progressive `edit_message_text` + final `send_message` reply |
| Webhooks | `POST /api/v1/webhooks/{provider}` (HMAC) | Surfaced into the same `Channel`/`turn_runner` pipeline |

Every surface runs through the same `channels/turn_runner.run_turn(...)`:
1. Load history (verbatim window or LCM-compacted).
2. Persist user message + assistant placeholder.
3. Open OTel `turn_span` + `llm.chat_span`.
4. Stream provider events through the aggregator + verbose-level filter.
5. `channel.deliver(...)` translates `StreamEvent → bytes` for the surface.
6. Finalize: patch the assistant row, write cost ledger, fire `TurnCompletedEvent`, schedule LCM compaction.

---

## API overview

```
# Auth (fastapi-users)
POST   /auth/register
POST   /auth/jwt/login
POST   /auth/jwt/logout
POST   /auth/forgot-password / /reset-password
GET    /auth/oauth/{google|apple}/start
GET    /auth/oauth/{google|apple}/callback

# Conversations
GET    /api/v1/conversations
POST   /api/v1/conversations
GET    /api/v1/conversations/:id
PATCH  /api/v1/conversations/:id
DELETE /api/v1/conversations/:id

# Chat
POST   /api/v1/chat                                  # SSE stream

# Models
GET    /api/v1/models                                # Catalog

# Workspace
GET    /api/v1/workspace                             # List user workspaces
POST   /api/v1/workspace                             # Create
GET    /api/v1/workspaces/{workspace_id}/env         # List env keys
PUT    /api/v1/workspaces/{workspace_id}/env         # Set/merge env keys

# Channels (Telegram binding etc.)
POST   /api/v1/channels/telegram/link                # Generate code
GET    /api/v1/channels                              # List bindings
DELETE /api/v1/channels/{binding_id}

# Cost / audit / health
GET    /api/v1/cost                                  # Spend summary
GET    /api/v1/cost/ledger                           # Paginated rows
GET    /api/v1/audit                                 # Audit events
GET    /api/v1/health
GET    /api/v1/health/ready

# Plus: projects, personalization, appearance, exports, stt, scheduled_jobs, webhooks
```

---

## Commands

```bash
# Dev / build
just dev              # Frontend + backend with hot reload
just dev-telegram     # Force Telegram polling locally
just install          # bun install + uv sync
just clean            # Drop build caches

# Quality
just check            # Biome + ruff (read-only)
just check-all        # check + bandit + mypy
just lint / lint-fix  # Biome + ruff
just format           # Auto-format

# Tests
just test             # pytest (backend)
bun run test          # vitest (frontend)

# Architecture
just sentrux          # Sentrux quality + rule check
just arch-be          # import-linter (backend layers)
just arch-fe          # dependency-cruiser (frontend layers)
just arch             # all three

# Desktop
just electrobun-dev   # Run desktop shell against `just dev`
just electrobun-dist  # Build a packaged shell

# Git
just commit           # Conventional-commit assistant
just push             # Push with multi-account auth handling
```

---

## Deployment

### Railway (production)
- One service per repo (backend Dockerfile).
- `backend/railway.toml` sets the `startCommand`. Migrations run at boot via `alembic upgrade head` (the graph is single-head as of `016_merge_notion_into_lcm_lineage` + `001` reparenting); an advisory lock in `alembic/env.py` serialises concurrent replicas during rolling deploys.
- Workspaces persist on a mounted volume (set `WORKSPACE_BASE_DIR=/data/workspaces` and attach a Railway volume).

### Docker Compose
- **dev** — Postgres + backend, ports published locally, source-bind hot reload.
- **prod** — Postgres + backend (2-worker uvicorn, memory-capped) + Next.js + nginx (`:80`). No published DB port; nginx is the only public surface.
- **demo** — `DEMO_MODE=true`, low rate limits, no Telegram, outbound network blocked at tool layer.

### Self-hosted CI runners
This repo is wired to a self-hosted runner pool on the operator's VPS. Add a runner with:
```bash
sudo GH_TOKEN=ghp_… REPO=OctavianTocan/Pawrrtal-AI \
  RUNNER_NAME=openclaw-vps-XX \
  bash scripts/install-self-hosted-runner.sh
```
Each runner gets an isolated `$HOME` via a systemd override so concurrent jobs don't race on `~/.bun/`. See `frontend/content/docs/handbook/ci/self-hosted-runner.md`.

---

## CI & quality gates

| Workflow | What it gates | Runner |
|---|---|---|
| `check.yml` | Frontend: Biome + `tsc --noEmit` + file-line + nesting + view-container | self-hosted |
| `backend-check.yml` | Backend: ruff lint + ruff format | self-hosted |
| `tests.yml` | Backend pytest + Frontend Vitest | self-hosted |
| `integration-tests.yml` | Backend live-LLM integration suite | self-hosted (gated) |
| `stagehand-e2e.yml` | Stagehand AI-driven E2E | ubuntu-latest |
| `dev-console-smoke.yml` | `next dev` boots with no fatal warnings | self-hosted |
| `sentrux.yml` | Sentrux rules + import-linter + dependency-cruiser | self-hosted |
| `design-lint.yml` | `DESIGN.md` spec validation | ubuntu-latest |
| `react-doctor.yml` | React patterns (key uniqueness, etc.) | self-hosted |
| `rebase.yml` | Auto-rebase PRs against `development` | n/a |
| `claude.yml` | `@claude`-mention bot (manual trigger only) | self-hosted |

Every workflow is actor-gated (`OctavianTocan` only) so public-repo forks can't spend the runner budget.

### Local "what'll fail in CI" gates
- `scripts/check-file-lines.mjs` — 500-line hard ceiling per `.ts`/`.tsx`/`.py`.
- `scripts/check-nesting.{mjs,py}` — max depth-3 compound statements per function.
- `scripts/check-view-container.mjs` — heavy hooks live in containers, not views.
- `scripts/check-no-tools-in-providers.py` — providers may not import from `app.core.tools.*`.
- `scripts/dev-console-smoke.mjs` — boots `next dev` and fails on `console.error` / hydration warnings.

---

## Testing

- **Backend** — `uv run pytest` (in-memory SQLite). Agent-loop tests use the `ScriptedStreamFn` pattern at the `_stream_fn` seam — the real loop runs; only the LLM trajectory is scripted. See `backend/tests/agent_harness.py` and `.claude/rules/testing/agent-loop-testing-philosophy.md`.
- **Frontend** — Vitest + Testing Library (`frontend/test/setup.ts` polyfills ResizeObserver, matchMedia, etc.).
- **E2E** — Stagehand (LLM-driven Playwright). Soft-passes if no LLM keys are present.
- **Integration** — `backend/tests/integration/` hits live providers (Claude Haiku) when `RUN_INTEGRATION_TESTS=1` is set or the workflow is manually dispatched.

---

## Documentation

- **README.md** (this file).
- **CHANGELOG.md** — release notes (Unreleased + tagged).
- **DESIGN.md** — design tokens; canonical values live in `frontend/app/globals.css`. `bun run design:lint` validates.
- **AGENTS.md** / **CLAUDE.md** (symlink) — repo conventions every agent reads at session start.
- **`docs/`** — plans, ADRs, deployment guides, Docker recipe, hyperframes/ (demo-reel rig).
- **In-app handbook** (`frontend/content/docs/handbook/`) — served by Fumadocs. ADRs under `handbook/decisions/`.
- **`.claude/rules/`** — agent rules, scoped by `paths:` globs in YAML frontmatter so they only fire on relevant files.

---

## License

MIT
