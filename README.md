# ![logo](assets/pawrrtal-icon.png "logo") Pawrrtal

```
▗▄▄▖  ▗▄▖ ▗▖ ▗▖▗▄▄▖ ▗▄▄▖▗▄▄▄▖▗▄▖ ▗▖        ▗▄▖ ▗▄▄▄▖
▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌ █ ▐▌ ▐▌▐▌       ▐▌ ▐▌  █  
▐▛▀▘ ▐▛▀▜▌▐▌ ▐▌▐▛▀▚▖▐▛▀▚▖ █ ▐▛▀▜▌▐▌       ▐▛▀▜▌  █  
▐▌   ▐▌ ▐▌▐▙█▟▌▐▌ ▐▌▐▌ ▐▌ █ ▐▌ ▐▌▐▙▄▄▖    ▐▌ ▐▌▗▄█▄▖



```

<p align="center">
  <a href="docs/assets/header.mp4" title="Click for the full-resolution MP4">
    <img src="docs/assets/header.gif" alt="Pawrrtal demo" width="100%" />
  </a>
</p>

[![Formatted with Biome](https://img.shields.io/badge/Formatted_with-Biome-60a5fa?style=flat&logo=biome)](https://biomejs.dev/)
[![Linted with Biome](https://img.shields.io/badge/Linted_with-Biome-60a5fa?style=flat&logo=biome)](https://biomejs.dev)
[![Sentrux](https://img.shields.io/badge/Architecture-Sentrux-7c3aed?style=flat)](https://github.com/sentrux/sentrux)

**Pawrrtal** is a personal AI assistant, a "Paw" of your own, that runs across the web, desktop shells, Telegram, scheduled jobs, and webhook-triggered workflows. Every user gets their own **workspace**: a filesystem-backed agent home with memory, skills, artifacts, tasks, and encrypted credentials. The agent reads and writes through a workspace-scoped tool layer, calls curated tools, and reasons against workspace context (`SOUL.md`, `AGENTS.md`, `BOOTSTRAP.md`, skills) instead of a one-size-fits-all system prompt.

> **Pawrrtal vs an "AI chatbot"**: Pawrrtal is not just a Gemini wrapper. It runs a provider-agnostic agent loop over a stable `AgentTool` contract, supports Claude and Gemini through one model catalog, resolves provider keys per workspace, exposes plugin tools, streams over web/electron and Telegram, and keeps governance data such as cost, audit events, and traces in the same FastAPI core.

---

## Current status

This README documents the current `development` branch feature surface. Some features are always on, some are key-gated, and some are present but intentionally disabled by default.

Always-on core: web chat, conversations, model catalog, workspaces, workspace file APIs, artifact rendering, MarkItDown conversion, current-time tool, task tools, skill discovery tools, cost/audit APIs, health probes, and settings sections that are wired in the frontend.

Key-gated: Claude (`CLAUDE_CODE_OAUTH_TOKEN`), Gemini (`GEMINI_API_KEY`), xAI Grok (`XAI_API_KEY`), OpenAI chat via LiteLLM (`OPENAI_API_KEY`), OpenCode Go gateway (`OPENCODE_API_KEY`), Exa search (`EXA_API_KEY`), image generation (`OPENAI_CODEX_OAUTH_TOKEN`), xAI STT (`XAI_API_KEY`), Mistral/OpenAI voice backends, Notion (`NOTION_API_KEY`), Telegram (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_BOT_USERNAME`), OAuth providers, and webhook secrets.

Feature-flagged or off by default: LCM (`LCM_ENABLED=false`), scheduler (`SCHEDULER_ENABLED=false`), webhook receiver (`WEBHOOK_API_ENABLED=false`), chat rate limiting (`CHAT_RATE_LIMIT_PER_MINUTE=0`), Claude sandboxing (`CLAUDE_SANDBOX_ENABLED=false`), and in-process Python (`VIRTUAL_PYTHON_ENABLED=false`).

Known caveats: Apple OAuth callback is currently stubbed and returns 501. The event-bus `AgentHandler` path for webhook/scheduled agent turns is present, but should be verified before relying on it in production. The in-process Python tool is explicitly unsandboxed and should stay single-tenant/operator-only.

---

## Features

### Agent runtime

- **Multi-provider model catalog**: Anthropic Claude through `claude-agent-sdk`, Google Gemini through `google-genai`, xAI Grok through the official `xai-sdk` (gRPC), OpenAI chat models routed through the in-process LiteLLM SDK, and SST's OpenCode Go gateway (OpenAI-compatible) fronting open-weight coding models — all behind one `AILLM` protocol.
- **Current catalog entries**: Claude Opus 4.7, Claude Sonnet 4.6, Claude Haiku 4.5, Gemini 3 Flash Preview (default), Gemini 3.1 Flash Lite Preview, Grok 4.3, GPT-4o, GPT-4o mini, OpenAI o1, o1 mini, o3 mini, GLM-5.1 (z.ai, via OpenCode Go), and Kimi K2.6 (Moonshot, via OpenCode Go).
- **Canonical model IDs**: `host:vendor/model` IDs are used across the API, DB, logs, frontend, and Telegram picker.
- **Per-conversation model override**: Web and Telegram conversations can persist their own model choice.
- **Reasoning effort selection**: Web chat forwards the selected reasoning level on each turn.
- **Provider-agnostic tool layer**: Tools are expressed as `AgentTool`s and bridged into Claude/Gemini provider shapes. Provider files are kept tool-agnostic by architecture checks.
- **Streaming everywhere**: Web/electron stream Server-Sent Events. Telegram streams by progressive message edits and final replies.
- **Shared turn runner**: Web, electron, Telegram, and event-driven surfaces use the same turn pipeline for history loading, persistence, aggregation, cost recording, tracing, and finalization.
- **Safety limits**: Iteration cap, wall-clock budget, consecutive LLM/tool error budgets, retry backoff, and provider-specific governance settings are env-configurable.
- **Permission gates**: Per-turn tool permission checks are built from workspace context and applied across providers.
- **Multimodal input**: Web image attachments and Telegram photos are forwarded as provider-native multimodal inputs.

### Web app

- **Next.js app shell**: Authenticated chat shell with collapsible sidebar, mobile sheet behavior, history controls, workspace selector, help menu, keyboard shortcut dialog, and onboarding gates.
- **Fresh and existing chats**: `/` starts a new conversation with a generated UUID. `/c/:conversationId` server-fetches persisted messages and hydrates the chat UI.
- **Chat composer**: Controlled text composer with model picker, reasoning selector, image attachment handling, prompt suggestions, blocked-state messaging, and onboarding recovery.
- **SSE event handling**: The frontend parses `delta`, `thinking`, `tool_use`, `tool_result`, `artifact`, `error`, and `agent_terminated` stream events.
- **Conversation UI**: Shows assistant content, thinking, tool-call timeline, thinking duration, failed/streaming states, copy controls, and regenerate controls.
- **Artifacts**: `render_artifact` tool calls are lifted into dedicated artifact SSE events for structural client rendering. The artifact catalog includes interactive widgets — `ActionButton`, `ChoiceGroup`, `TextField`, and `NumberField` — that submit back into chat as follow-up user messages, with a stable `actionId` so the model can match interactions deterministically. Interactive widgets are gated to the web/electron surfaces; Telegram receives the read-only catalog so the model never emits unrenderable widgets.
- **Background recovery hooks**: In-flight prompts are tracked so interrupted streams can be recovered.
- **Whimsy/appearance overlay**: Chat and settings surfaces react to appearance texture settings.

### Telegram

Telegram is a first-class channel, not just a notification bridge.

- **Boot modes**: Polling for local/dev use and webhook mode for production.
- **Account binding**: Web settings issue one-time Telegram link codes and optional `https://t.me/<bot>?start=<code>` deep links. The bot accepts `/start <code>` and pasted codes.
- **Commands**: `/start`, `/new`, `/model`, `/models`, `/verbose 0|1|2`, `/stop`, `/status`, and `/lcm`.
- **Model picker**: `/models` opens an inline keyboard grouped by provider, backed by the same model catalog and ETag token.
- **Verbose levels**: 0 = quiet, 1 = tool calls, 2 = tool calls plus thinking.
- **Active-run cancellation**: `/stop` cancels the process-local `asyncio.Task` for the chat.
- **Typing indicator**: Long-running turns keep Telegram's typing indicator alive on a refresh loop.
- **Topic support**: Topic thread IDs are preserved, conversations can be per-topic, and auto-title can rename Telegram forum topics when the bot has rights.
- **Status surfaces**: `/status` reports gateway uptime, current model, verbose level, conversation age, message counts, token usage when available, and running/idle status. `/lcm` reports LCM context and summary state when LCM is enabled.
- **Inbound photos**: The largest Telegram photo is downloaded and forwarded to vision-capable models as base64 image input.
- **Inbound voice/audio**: Voice and audio files are transcribed through the configured voice backend when available, otherwise the agent receives bounded metadata annotations.
- **Inbound documents**: Documents under the size cap are converted to bounded Markdown via MarkItDown and inlined as annotations. Oversized or unsupported files fall back to metadata annotations.
- **Outbound media tools**: On Telegram turns, the agent can use `send_image_to_user`, `send_voice_to_user`, and `send_document_to_user` wrappers over the channel send function.

### Workspaces

- **Default workspace required for chat**: The chat endpoint returns 412 when onboarding has not produced a default workspace or the workspace directory is missing.
- **Multiple workspaces**: Users can list owned workspaces. The UI currently treats the default workspace as the active agent home.
- **Filesystem-backed agent home**: Workspaces are real directories under `{WORKSPACE_BASE_DIR}/{workspace_id}`.
- **Seeded context files**: Workspace prompt context is assembled from the workspace files, including core agent instructions, `SOUL.md`, `AGENTS.md`, `BOOTSTRAP.md`, settings, and skills metadata.
- **File tree API**: The web app can list workspace files as a flat tree.
- **Text file API**: UTF-8 files can be read, created/replaced, and deleted through authenticated workspace routes.
- **Binary serving**: Files from the default workspace can be served back with detected MIME type for images, audio, and other agent-produced artifacts.
- **Skill listing**: The workspace skill endpoint reads `skills/_manifest.jsonl` and falls back to directory discovery.
- **Encrypted workspace env**: Each workspace has its own Fernet-encrypted `.env` file with `0600` permissions.
- **Env resolution order**: workspace override, then gateway fallback where supported, then absent.
- **Overridable keys**: `GEMINI_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `OPENAI_API_KEY`, `XAI_API_KEY`, `OPENCODE_API_KEY`, `EXA_API_KEY`, `OPENAI_CODEX_OAUTH_TOKEN`, and `NOTION_API_KEY`.
- **`HEARTBEAT.md`**: Workspace-authored YAML front-matter file that declares cron-scheduled "check" prompts. `POST /api/v1/heartbeat/sync` parses it, ensures a dedicated heartbeat conversation exists, and reconciles `scheduled_jobs` rows so each check fires an agent turn into that conversation (and fans out to Telegram when the channel is linked). Cron expressions are validated against APScheduler at parse time.

### Agent tools

| Tool | Gating |
|---|---|
| `read_file` / `write_file` / `list_dir` | always, workspace-scoped |
| `render_artifact` | always |
| `markitdown_convert` | always |
| `now` | always |
| `add_task` / `list_tasks` / `complete_task` | always, backed by workspace `TASKS.md` |
| `list_skills` / `read_skill` / `invoke_skill` | always, no-op when no workspace skills exist |
| `cron_create` / `cron_list` / `cron_delete` | authenticated user present; live scheduling requires scheduler enabled |
| `send_message` | when the current surface supplies a `send_fn` |
| `send_image_to_user` / `send_voice_to_user` / `send_document_to_user` | Telegram surface only |
| `exa_search` | `EXA_API_KEY` via workspace or gateway |
| `image_gen` | `OPENAI_CODEX_OAUTH_TOKEN` via workspace |
| `python` | `VIRTUAL_PYTHON_ENABLED=true`, unsandboxed |
| `lcm_grep` / `lcm_describe` / `lcm_list_summaries` / `lcm_expand_query` | `LCM_ENABLED=true` + conversation id |
| Notion tools | `NOTION_API_KEY` via workspace |

Workspace file tools are scoped to the workspace root and reject absolute paths/traversal. The current code comments are deliberately honest: this is a strong invariant with unit tests, not yet a fully proven adversarial sandbox boundary.

### Plugin system

- **Registry-based plugins**: Plugins declare an id, display metadata, env keys, activation predicate, and tool factories.
- **Activation**: The default activation predicate enables a plugin when every declared required env key is present in the active workspace.
- **Tool composition**: Plugin tools are appended after core tools inside `build_agent_tools`.
- **Notion plugin**: The first plugin consumer. It activates on `NOTION_API_KEY`.
- **Notion tool surface**: `notion_search`, `notion_read`, `notion_append`, `notion_create`, `notion_read_markdown`, `notion_update_markdown`, `notion_update_page`, `notion_comment_create`, `notion_comment_list`, `notion_query`, `notion_delete`, `notion_move`, `notion_publish`, `notion_file_tree`, `notion_sync`, `notion_help`, `notion_doctor`, and `notion_logs_read`.
- **Execution model**: Notion calls run through the official `ntn` CLI with the token injected per call and temp-home isolation.
- **Auditability**: Notion operations are logged in `notion_operation_logs`.

### Voice and STT

- **Web STT endpoint**: `POST /api/v1/stt` accepts an uploaded audio file and returns transcript JSON.
- **xAI backend (default)**: `VOICE_PROVIDER=xai` uses the xAI STT HTTP endpoint via `XaiSttTranscriber`. The web `/api/v1/stt` route resolves `XAI_API_KEY` from the user's default workspace first then the gateway global; the Telegram bot reads the global setting.
- **Mistral backend**: `VOICE_PROVIDER=mistral` uses Mistral Voxtral when `VOICE_MISTRAL_API_KEY` is set and the optional dependency is installed.
- **OpenAI backend**: `VOICE_PROVIDER=openai` uses Whisper through the OpenAI SDK when `VOICE_OPENAI_API_KEY` is set and the optional dependency is installed.
- **Local backend**: `VOICE_PROVIDER=local` shells out to ffmpeg and whisper.cpp.
- **Telegram reuse**: Telegram voice/audio attachments use the same transcriber abstraction (including the xAI backend) and fall back to metadata annotations only when no key is configured.

### Lossless Context Management

LCM is a DAG-based conversation compaction system and is off by default.

- **Activation**: `LCM_ENABLED=true`.
- **Context assembly**: When enabled, older context is assembled from `lcm_context_items`; fresh tail messages stay verbatim.
- **Ingest**: User and assistant message rows are ingested into the LCM context list.
- **Compaction**: Turn finalization schedules background leaf compaction after assistant rows are finalized.
- **Agent tools**: `lcm_grep`, `lcm_describe`, `lcm_list_summaries`, and `lcm_expand_query` let the agent inspect compacted history.
- **Telegram diagnostics**: `/lcm` shows whether LCM is disabled, context item counts, raw vs compacted counts, summary-node breakdown, and latest summary metadata.

### Settings and UI surfaces

The settings route lives outside the chat shell and renders a two-pane settings UI.

Wired settings sections:

- **General**
- **Workspaces**
- **Appearance**: light/dark theme colors, fonts, options, whimsy texture controls, and reset to defaults.
- **Personalization**: name, company website, LinkedIn, role, goals, connected channels, ChatGPT context, personality, and custom instructions. Saving personalization also idempotently seeds the default workspace.
- **Integrations**
- **Channels**: Telegram link/unlink flow.
- **Archived chats**
- **Usage**

Placeholder settings sections currently listed in the nav but not fully wired:

- **Configuration**
- **MCP servers**
- **Git**
- **Environments**
- **Worktrees**
- **Browser use**

### Auth and access control

- **Password/JWT auth**: FastAPI Users powers register/login/logout/password flows and user routes.
- **Dev login**: `/auth/dev-login` logs in as the seeded admin in non-production when `ADMIN_EMAIL` and `ADMIN_PASSWORD` are configured. It also idempotently ensures a default workspace.
- **Google OAuth**: Start/callback flow is implemented and gated by `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.
- **Apple OAuth**: Start route exists, but callback is currently a stub returning 501.
- **Backend API key gate**: Optional `BACKEND_API_KEY` requires clients to send `X-Pawrrtal-Key`.
- **Email allowlist**: Optional `ALLOWED_EMAILS` restricts authenticated access.
- **Demo mode**: `DEMO_MODE=true` disables Telegram and applies demo deployment restrictions.

### Projects, conversations, and exports

- **Projects**: Users can list, create, rename, and delete projects. Deleting a project unlinks conversations rather than deleting them.
- **Conversation metadata**: Conversations store title, archived/flagged/unread state, status, labels, project id, model id, origin channel, Telegram thread id, and title source.
- **Message persistence**: Assistant messages persist content, thinking, tool calls, timeline, thinking duration, and assistant status.
- **Auto-title**: Web can generate a short title through a best-effort LLM call. Telegram can auto-title from the first user message and optionally rename topic threads.
- **Exports**: Conversations can be exported as Markdown, HTML, or JSON with a bounded message count.

### Governance, operations, and observability

- **Cost ledger**: Per-turn token/cost rows are persisted when cost tracking is enabled.
- **Cost budget gate**: Chat enforces per-request and per-user rolling-window cost caps and can return 402 on overage.
- **Cost API**: `GET /api/v1/cost/` returns rolling-window summary and optional per-model breakdown. `GET /api/v1/cost/ledger` returns paginated raw rows.
- **Audit API**: `GET /api/v1/audit/` returns user-scoped events. `GET /api/v1/audit/summary` returns counts by event type and risk level.
- **Secret redaction**: Tool inputs/log output can be redacted when `SECRET_REDACTION_ENABLED=true`.
- **Request logging**: Every request gets a request id for log correlation.
- **Health probes**: `/api/v1/health` is liveness. `/api/v1/health/ready` checks DB connectivity and at least one configured LLM provider.
- **OpenTelemetry**: Traces include `pawrrtal.turn` and `pawrrtal.llm.chat` spans, model/user/conversation/surface metadata, usage, cost, and Workshop/OpenLLMetry-compatible event hooks.
- **Event bus**: A process-local async pub/sub bus publishes turn, webhook, scheduled, and agent-response events.
- **Webhook receiver**: `WEBHOOK_API_ENABLED=true` enables `/webhooks/{provider}`. GitHub uses HMAC-SHA256. Generic providers use a bearer secret. Deliveries are deduped before publishing to the event bus.
- **Scheduler**: `SCHEDULER_ENABLED=true` starts a cron scheduler. The API can list historical jobs regardless of the flag, but create/delete live jobs require a running scheduler.

### Desktop shells

- **Electron**: Native desktop shell with preload/IPC and macOS-aware window chrome.
- **Electrobun**: Bun + system webview shell for a smaller desktop runtime.
- **Portable frontend contract**: Desktop-only IPC goes through `frontend/lib/desktop.ts` with web fallbacks so the React app stays portable.

---

## Tech stack

| Layer       | Stack |
|-------------|-------|
| Frontend    | Next.js 16, React 19, Tailwind v4, TanStack Query, Fumadocs |
| Backend     | FastAPI, Python 3.13, SQLAlchemy 2 async, Alembic, fastapi-users |
| Database    | PostgreSQL (prod, Railway), SQLite + aiosqlite (tests / fresh dev) |
| Providers   | `claude-agent-sdk` (Anthropic), `google-genai` (Gemini), `xai-sdk` (Grok, gRPC), `litellm` (OpenAI chat), OpenCode Go gateway (GLM-5.1, Kimi K2.6) |
| Channels    | aiogram (Telegram polling or webhook), SSE (web/electron) |
| Voice        | xAI STT, Mistral Voxtral, OpenAI Whisper, local whisper.cpp |
| Encryption  | Fernet (workspace `.env`) |
| Desktop     | Electron, Electrobun |
| Toolchain   | Bun, uv, Biome, Ruff, mypy strict, Bandit, just, Lefthook |
| Arch gates  | Sentrux, import-linter, dependency-cruiser, custom repo checks |

---

## Quick start

### Prerequisites

- [Bun](https://bun.sh) for the frontend runtime and package manager.
- [uv](https://docs.astral.sh/uv/) for Python package and venv management.
- Python 3.13+.
- Postgres 16 for prod-like dev, or nothing extra if using SQLite for local tests.
- At least one model provider key: `GEMINI_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`.

### Install

```bash
git clone --recurse-submodules https://github.com/OctavianTocan/Pawrrtal-AI.git pawrrtal
cd pawrrtal

# Vendored submodules: react-overlay, react-dropdown, react-chat-composer.
# If you forgot --recurse-submodules:
git submodule update --init --recursive

just install
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# Fill in AUTH_SECRET, WORKSPACE_ENCRYPTION_KEY, CORS_ORIGINS, and at least one provider key.
```

### Run dev

```bash
just dev
# or
bun run dev
```

The dev orchestrator clears stale ports, removes the Next.js dev lock, and launches Next.js on `:3001` plus FastAPI on `:8000` with hot reload. Local dev uses plain `localhost`.

### Docker

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The dev compose stack runs Postgres on `:5432` and backend on `:8000`. The prod overlay adds the Next.js service and nginx reverse proxy on `:80`.

### Logs

Backend writes a rotated combined log to `backend/app.log`:

```bash
tail -f backend/app.log
```

---

## Configuration

Every backend setting lives on `backend/app/core/config.py::Settings`. The full annotated reference is `backend/.env.example`; `backend/.env.docker.example` is the Compose quick-start subset; `docs/docker.md` groups settings by concern.

Required-at-minimum for a useful local app: `AUTH_SECRET`, `WORKSPACE_ENCRYPTION_KEY`, `CORS_ORIGINS`, and at least one provider key.

```bash
# Auth + access
AUTH_SECRET=
WORKSPACE_ENCRYPTION_KEY=
BACKEND_API_KEY=
ALLOWED_EMAILS=
DEMO_MODE=false

# Database
DATABASE_URL=postgresql+psycopg://...
SQLITE_DB_FILENAME=pawrrtal.db

# Workspace
WORKSPACE_BASE_DIR=/data/workspaces
WORKSPACE_CONTEXT_ENABLED=true
WORKSPACE_SKILLS_DIR_NAME=.claude/skills
WORKSPACE_SETTINGS_FILENAME=.claude/settings.json

# Providers and tool keys
GEMINI_API_KEY=
CLAUDE_CODE_OAUTH_TOKEN=
OPENAI_API_KEY=                  # OpenAI chat via LiteLLM
XAI_API_KEY=                     # Grok chat + xAI STT
OPENCODE_API_KEY=                # SST OpenCode Go gateway (GLM-5.1, Kimi K2.6)
OPENCODE_GO_BASE_URL=https://opencode.ai/zen/go/v1
EXA_API_KEY=
OPENAI_CODEX_OAUTH_TOKEN=        # workspace-only by default
NOTION_API_KEY=                  # workspace-only plugin key

# CORS / cookies
CORS_ORIGINS=["http://localhost:3001"]
CORS_ORIGIN_REGEX=^https:\/\/.*\.vercel\.app$
COOKIE_DOMAIN=
COOKIE_SAMESITE=lax
COOKIE_SECURE=false

# Channels: Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_MODE=polling
TELEGRAM_WEBHOOK_URL=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_VERBOSE_DEFAULT=1
TELEGRAM_TYPING_REFRESH_SECONDS=2.5
TELEGRAM_USE_DRAFT_STREAMING=false

# Agent loop safety
AGENT_MAX_ITERATIONS=25
AGENT_MAX_WALL_CLOCK_SECONDS=300
AGENT_MAX_CONSECUTIVE_LLM_ERRORS=3
AGENT_MAX_CONSECUTIVE_TOOL_ERRORS=5
AGENT_LLM_RETRY_BACKOFF_SECONDS=1.0

# Claude SDK governance
CLAUDE_SANDBOX_ENABLED=false
CLAUDE_SANDBOX_AUTO_ALLOW_BASH=true
CLAUDE_SANDBOX_EXCLUDED_COMMANDS=sudo,ssh,scp,rsync
CLAUDE_RETRY_MAX_ATTEMPTS=3
CLAUDE_RETRY_BASE_DELAY_SECONDS=1.0
CLAUDE_RETRY_MAX_DELAY_SECONDS=30.0
CLAUDE_RETRY_BACKOFF_FACTOR=2.0

# Chat rate limiting
CHAT_RATE_LIMIT_PER_MINUTE=0

# Cost + audit + redaction
COST_TRACKER_ENABLED=true
COST_MAX_PER_REQUEST_USD=1.0
COST_MAX_PER_USER_DAILY_USD=10.0
COST_RESET_WINDOW_HOURS=24
AUDIT_LOG_ENABLED=true
AUDIT_LOG_RETENTION_DAYS=90
SECRET_REDACTION_ENABLED=true
STRICT_CONVERSATION_READ_VALIDATION=true

# Ops platform
WEBHOOK_API_ENABLED=false
WEBHOOK_API_SECRET=
GITHUB_WEBHOOK_SECRET=
SCHEDULER_ENABLED=false
SCHEDULER_PERSISTENT_JOBSTORE=true

# OAuth
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/oauth/google/callback
APPLE_OAUTH_CLIENT_ID=
APPLE_OAUTH_TEAM_ID=
APPLE_OAUTH_KEY_ID=
APPLE_OAUTH_PRIVATE_KEY=
APPLE_OAUTH_REDIRECT_URI=
OAUTH_POST_LOGIN_REDIRECT=http://localhost:3001/

# Voice / STT
VOICE_PROVIDER=xai
VOICE_MISTRAL_API_KEY=
VOICE_OPENAI_API_KEY=
VOICE_WHISPER_CPP_BINARY=
VOICE_WHISPER_CPP_MODEL=base
VOICE_MAX_SIZE_MB=25

# LCM
LCM_ENABLED=false
LCM_FRESH_TAIL_COUNT=64
LCM_LEAF_CHUNK_TOKENS=20000
LCM_CONTEXT_THRESHOLD=0.75
LCM_INCREMENTAL_MAX_DEPTH=1
LCM_SUMMARY_MODEL=

# In-process Python tool
VIRTUAL_PYTHON_ENABLED=false
VIRTUAL_PYTHON_TIMEOUT_SECONDS=30
VIRTUAL_PYTHON_OUTPUT_CAP_BYTES=32000

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=
OTEL_EXPORTER_OTLP_PROTOCOL=http/json
OTEL_SERVICE_NAME=pawrrtal-backend
OTEL_EXPORTER_OTLP_HEADERS=

# Dev admin login, disabled when ENV=prod
ADMIN_EMAIL=admin@pawrrtal-ai.dev
ADMIN_PASSWORD=admin1234
```

### Per-workspace API keys

Provider and integration keys can be stored per workspace in the encrypted `.env` file. The frontend exposes these through Settings. Tool and provider resolution prefers workspace keys over gateway keys. Plugin keys such as `NOTION_API_KEY` are workspace-only by design.

---

## Architecture

### Request to response, web chat turn

```
Browser ─SSE─▶ Next.js (:3001) ─fetch─▶ FastAPI /api/v1/chat
                                              │
                       ┌──────────────────────┼──────────────────────┐
                       ▼                      ▼                      ▼
              _require_workspace       resolve_llm()        build_agent_tools()
              (412 if missing)        (workspace_id +       (workspace files,
                                       workspace_root)       tasks, skills, Exa,
                                                             image-gen, Notion,
                                                             LCM, cron, ...)
                                              │
                                              ▼
                                  Channel.deliver(
                                      provider.stream(...)
                                        └─ agent_loop(...)
                                             └─ StreamFn ────────────┐
                                                                     │
                                                          Claude SDK / Gemini API
```

`chat.py` resolves workspace, enforces the cost gate, resolves the provider, composes tools, builds the permission check, forwards multimodal images, publishes `TurnStartedEvent`, and hands the request to `run_turn`. The turn runner loads history or LCM context, persists the user row and assistant placeholder, streams provider events through the aggregator and channel, finalizes the assistant row, writes cost, publishes `TurnCompletedEvent`, and schedules LCM compaction when enabled.

### Repo layout

```
pawrrtal/
├─ backend/
│  ├─ main.py                       # FastAPI app composition + lifespan
│  ├─ app/
│  │  ├─ api/                       # Routers: chat, conversations, models,
│  │  │                             # workspace, env, channels, cost, audit,
│  │  │                             # stt, oauth, projects, exports, jobs, health
│  │  ├─ channels/                  # Channel protocol, turn_runner, sse, telegram
│  │  ├─ core/
│  │  │  ├─ agent_loop/             # Provider-neutral loop, types, safety
│  │  │  ├─ agent_tools.py          # Per-turn tool composition
│  │  │  ├─ event_bus/              # Typed pub/sub for turns, webhooks, jobs
│  │  │  ├─ plugins/                # Plugin registry + types
│  │  │  ├─ providers/              # ClaudeLLM, GeminiLLM, catalog, model_id
│  │  │  └─ tools/                  # Concrete tool implementations
│  │  ├─ crud/                      # SQLAlchemy CRUD per domain
│  │  ├─ integrations/
│  │  │  ├─ notion/                 # Notion plugin via ntn CLI
│  │  │  ├─ telegram/               # aiogram bot, handlers, status, model picker
│  │  │  ├─ voice/                  # Mistral, OpenAI, whisper.cpp transcribers
│  │  │  └─ webhooks/               # HMAC/Bearer webhook receiver
│  │  ├─ governance_models.py       # audit_events, cost_ledger, scheduled_jobs, ...
│  │  ├─ models.py                  # User, Conversation, Message, Workspace, LCM, ...
│  │  └─ schemas.py                 # Pydantic API schemas
│  ├─ alembic/
│  ├─ Dockerfile
│  └─ railway.toml
├─ frontend/
│  ├─ app/                          # Next.js App Router
│  │  ├─ (app)/                     # Chat shell routes
│  │  ├─ (auth)/                    # Login / signup
│  │  ├─ settings/                  # Settings page outside chat shell
│  │  └─ api/                       # Next.js route handlers
│  ├─ features/                     # chat, nav-chats, onboarding, settings, whimsy, ...
│  ├─ components/                   # ai-elements, brand-icons, ui primitives
│  ├─ hooks/                        # useAuthedFetch, useAuthedQuery, ...
│  ├─ lib/                          # api.ts, desktop.ts, types.ts, ai-utils, ...
│  └─ content/docs/handbook/        # In-app handbook
├─ electron/
├─ electrobun/
├─ docs/
├─ scripts/
├─ docker-compose.{yml,dev,prod,demo}.yml
├─ nginx/
├─ justfile
├─ DESIGN.md
├─ AGENTS.md / CLAUDE.md
└─ CHANGELOG.md
```

---

## API overview

```bash
# Auth
POST   /auth/register
POST   /auth/jwt/login
POST   /auth/jwt/logout
POST   /auth/forgot-password
POST   /auth/reset-password
POST   /auth/dev-login                         # non-prod only
GET    /api/v1/auth/oauth/google/start
GET    /api/v1/auth/oauth/google/callback
GET    /api/v1/auth/oauth/apple/start
POST   /api/v1/auth/oauth/apple/callback       # currently stubbed: 501
GET    /users/me
PATCH  /users/me

# Conversations + chat
GET    /api/v1/conversations
POST   /api/v1/conversations/:id
GET    /api/v1/conversations/:id
PATCH  /api/v1/conversations/:id
DELETE /api/v1/conversations/:id
GET    /api/v1/conversations/:id/messages
POST   /api/v1/conversations/:id/title
GET    /api/v1/conversations/:id/export?format=md|html|json
POST   /api/v1/chat/                            # SSE stream

# Models
GET    /api/v1/models

# Projects
GET    /api/v1/projects
POST   /api/v1/projects
PATCH  /api/v1/projects/:id
DELETE /api/v1/projects/:id

# Personalization + appearance
GET    /api/v1/personalization
PUT    /api/v1/personalization
GET    /api/v1/appearance
PUT    /api/v1/appearance
DELETE /api/v1/appearance

# Workspaces
GET    /api/v1/workspaces
GET    /api/v1/workspaces/onboarding-status
GET    /api/v1/workspaces/:workspace_id/tree
GET    /api/v1/workspaces/:workspace_id/files/:file_path
PUT    /api/v1/workspaces/:workspace_id/files/:file_path
DELETE /api/v1/workspaces/:workspace_id/files/:file_path
GET    /api/v1/workspaces/:workspace_id/skills
GET    /api/v1/workspaces/default/serve/:file_path
GET    /api/v1/workspaces/:workspace_id/env
PUT    /api/v1/workspaces/:workspace_id/env
DELETE /api/v1/workspaces/:workspace_id/env/:key

# Channels
GET    /api/v1/channels
POST   /api/v1/channels/telegram/link
DELETE /api/v1/channels/telegram/link
POST   /api/v1/channels/telegram/webhook        # Telegram webhook mode only

# Voice / STT
POST   /api/v1/stt

# Cost / audit / scheduler / webhooks / health
GET    /api/v1/cost/
GET    /api/v1/cost/ledger
GET    /api/v1/audit/
GET    /api/v1/audit/summary
GET    /api/v1/scheduled-jobs/
POST   /api/v1/scheduled-jobs/                  # scheduler enabled only
DELETE /api/v1/scheduled-jobs/:id
POST   /api/v1/heartbeat/sync                   # reconcile HEARTBEAT.md → scheduled_jobs
POST   /webhooks/:provider                      # webhook API enabled only
GET    /api/v1/health
GET    /api/v1/health/ready
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
just electrobun-dev   # Run desktop shell against just dev
just electrobun-dist  # Build a packaged shell

# Git
just commit           # Conventional-commit assistant
just push             # Push with multi-account auth handling
```

---

## Deployment

### Railway

- One service per repo using the backend Dockerfile.
- `backend/railway.toml` sets the start command.
- Migrations run at boot via `alembic upgrade head`.
- Workspaces persist on a mounted volume. Set `WORKSPACE_BASE_DIR=/data/workspaces` and attach a Railway volume.

### Docker Compose

- **dev**: Postgres + backend, ports published locally, source-bind hot reload.
- **prod**: Postgres + backend + Next.js + nginx. No published DB port; nginx is the public surface.
- **demo**: `DEMO_MODE=true`, low rate limits, no Telegram, outbound network blocked at tool layer.

### Self-hosted CI runners

This repo is wired to a self-hosted runner pool on the operator's VPS. Add a runner with:

```bash
sudo GH_TOKEN=ghp_… REPO=OctavianTocan/Pawrrtal-AI \
  RUNNER_NAME=openclaw-vps-XX \
  bash scripts/install-self-hosted-runner.sh
```

Each runner gets an isolated `$HOME` via a systemd override so concurrent jobs do not race on `~/.bun/`. See `frontend/content/docs/handbook/ci/self-hosted-runner.md`.

---

## CI and quality gates

| Workflow | What it gates | Runner |
|---|---|---|
| `check.yml` | Frontend: Biome + `tsc --noEmit` + file-line + nesting + view-container | self-hosted |
| `backend-check.yml` | Backend: ruff lint + ruff format | self-hosted |
| `tests.yml` | Backend pytest + frontend Vitest | self-hosted |
| `integration-tests.yml` | Backend live-LLM integration suite | self-hosted, gated |
| `stagehand-e2e.yml` | Stagehand AI-driven E2E | ubuntu-latest |
| `dev-console-smoke.yml` | `next dev` boots with no fatal warnings | self-hosted |
| `sentrux.yml` | Sentrux rules + import-linter + dependency-cruiser | self-hosted |
| `design-lint.yml` | `DESIGN.md` spec validation | ubuntu-latest |
| `react-doctor.yml` | React pattern checks | self-hosted |
| `rebase.yml` | Auto-rebase PRs against `development` | n/a |
| `claude.yml` | `@claude` mention bot, manual trigger only | self-hosted |

Every workflow is actor-gated to `OctavianTocan` so public-repo forks cannot spend runner budget.

### Local checks

- `scripts/check-file-lines.mjs`: 500-line hard ceiling per `.ts`, `.tsx`, and `.py` file.
- `scripts/check-nesting.{mjs,py}`: max depth-3 compound statements per function.
- `scripts/check-view-container.mjs`: heavy hooks live in containers, not views.
- `scripts/check-no-tools-in-providers.py`: providers may not import from `app.core.tools.*`.
- `scripts/dev-console-smoke.mjs`: boots `next dev` and fails on `console.error` or hydration warnings.

---

## Testing

- **Backend**: `uv run pytest` using in-memory SQLite. Agent-loop tests use the `ScriptedStreamFn` seam so the real loop runs while the LLM trajectory is scripted.
- **Frontend**: Vitest + Testing Library. `frontend/test/setup.ts` polyfills browser APIs.
- **E2E**: Stagehand-driven Playwright. Soft-passes if no LLM keys are present.
- **Integration**: `backend/tests/integration/` hits live providers when `RUN_INTEGRATION_TESTS=1` is set or the workflow is manually dispatched.

---

## Documentation

- **README.md**: this file.
- **CHANGELOG.md**: release notes.
- **DESIGN.md**: design tokens. Canonical values live in `frontend/app/globals.css`; `bun run design:lint` validates.
- **AGENTS.md / CLAUDE.md**: repo conventions for agents.
- **docs/**: plans, ADRs, deployment guides, Docker recipe, and hyperframes/demo-reel rig.
- **frontend/content/docs/handbook/**: in-app handbook served by Fumadocs.
- **.claude/rules/**: path-scoped agent rules.

---

## License

MIT
