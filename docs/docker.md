# Running Pawrrtal with Docker Compose

The repo ships three compose files:

| File | Stack | Use case |
|---|---|---|
| `docker-compose.yml` | Postgres 16 + FastAPI backend | Base — same services every overlay extends |
| `docker-compose.dev.yml` | + ports `5432`, `8000` published locally; source bind-mount + `uvicorn --reload` | Local dev where you run the Next.js frontend with hot-reload from your host |
| `docker-compose.demo.yml` | + `DEMO_MODE=true`, low rate limits, no Telegram, ephemeral workspace, outbound network blocked at the tool layer | Public demo deployments |

The Next.js frontend is left out of the base/dev stacks intentionally —
you run it on the host so hot-reload keeps working.

Public VPS deployment does not use a Compose reverse proxy. Run the
frontend and backend on loopback, then publish them with:

```bash
paw project cloudflared install --hostname <pawrrtal-hostname> --tunnel-name pawrrtal
```

Cloudflare Access is the public gate for that hostname.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose plugin)
- At least one of: `GOOGLE_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`. Everything else is optional.

## Quick start

```bash
# 1. Clone the repo (use --recurse-submodules for vendored frontend packages)
git clone --recurse-submodules https://github.com/OctavianTocan/Pawrrtal-AI.git
cd pawrrtal

# Plain clone? Run: git submodule update --init --recursive

# 2. Copy the Docker environment template and fill in your API keys
cp backend/.env.docker backend/.env
$EDITOR backend/.env   # set GOOGLE_API_KEY at minimum

# 3. Build and start the stack (base + dev overlay)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The backend will be live at **http://localhost:8000** and PostgreSQL will be
exposed at **localhost:5432** (credentials: `pawrrtal` / `pawrrtal_dev`, database `pawrrtal`).

Database migrations run automatically on every backend start via
`alembic upgrade head`. The migration graph is single-head as of
`016_merge_notion_into_lcm_lineage`, and a Postgres advisory lock in
`alembic/env.py` serialises concurrent invocations across rolling-deploy
replicas, so a stuck partial migration won't break the next replica.

The dev stack starts uvicorn with `--reload` and mounts `./backend/app`
into the container, so Python edits take effect on the next request
without a rebuild.

## Frontend

In a separate terminal:

```bash
cd pawrrtal
bun install          # or npm install
bun dev              # or npm run dev
```

The project dev server starts at **http://localhost:3000** and uses same-origin
browser API paths. Next.js rewrites `/api/v1`, `/auth`, and `/users` to
`BACKEND_INTERNAL_URL`, which defaults to **http://127.0.0.1:8000**.

## Useful commands

```bash
# View live backend logs
docker compose logs -f backend

# Open a psql shell against the local postgres
docker compose exec postgres psql -U pawrrtal -d pawrrtal

# Run Alembic migrations manually (useful after pulling new code)
docker compose exec backend alembic upgrade head

# Rebuild after changing Python dependencies
docker compose build backend
docker compose up -d

# Stop everything and remove volumes (wipes the DB)
docker compose down -v

# Stop but keep the DB volume
docker compose down
```

## Environment variables

Every variable below maps to a field on
[`backend/app/core/config.py::Settings`](../backend/app/core/config.py).
`backend/.env.example` is the **full reference** (one entry per Settings
field with inline docs); `backend/.env.docker.example` is the Compose
quick-start subset. This page is the cheat-sheet view, grouped by
concern.

### Required for any deploy

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres URL. Overridden by `docker-compose.yml` to point at the bundled service. |
| `AUTH_SECRET` | JWT signing secret. Generate: `openssl rand -hex 32`. |
| `WORKSPACE_ENCRYPTION_KEY` | Fernet key for per-workspace encrypted `.env` files. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `GOOGLE_API_KEY` | Powers every Gemini model in the default catalog. |
| `CORS_ORIGINS` | JSON array of allowed browser origins. |

### LLM providers (at least one provider needed for chat to be useful)

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Gemini — default model uses it. |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Agent SDK — required for any `claude-*` model. Generate: `claude setup-token`. |
| `EXA_API_KEY` | Web search via the provider-agnostic `exa_search` tool. |
| `XAI_API_KEY` | xAI; also powers voice STT when `VOICE_PROVIDER=xai`. |

### Cookies, CORS, environment

`ENV`, `COOKIE_DOMAIN`, `COOKIE_SAMESITE`, `COOKIE_SECURE`,
`CORS_ORIGINS`, `CORS_ORIGIN_REGEX`, `WORKSPACE_BASE_DIR`.

### Access control

`ALLOWED_EMAILS` (comma-separated email allowlist), `DEMO_MODE` (locks
down public demo deploys). `BACKEND_API_KEY` is optional and only fits
server-to-server callers that can inject `X-Pawrrtal-Key`; leave it
unset for the Cloudflared browser app.

### Agent loop safety (defaults work for most deploys)

`AGENT_MAX_ITERATIONS=25`, `AGENT_MAX_WALL_CLOCK_SECONDS=300`,
`AGENT_MAX_CONSECUTIVE_LLM_ERRORS=3`,
`AGENT_MAX_CONSECUTIVE_TOOL_ERRORS=5`,
`AGENT_LLM_RETRY_BACKOFF_SECONDS=1.0`. Empty string disables a guard.

### Claude SDK governance

`CLAUDE_SANDBOX_ENABLED`, `CLAUDE_SANDBOX_AUTO_ALLOW_BASH`,
`CLAUDE_SANDBOX_EXCLUDED_COMMANDS`, `CLAUDE_RETRY_MAX_ATTEMPTS`,
`CLAUDE_RETRY_BASE_DELAY_SECONDS`, `CLAUDE_RETRY_MAX_DELAY_SECONDS`,
`CLAUDE_RETRY_BACKOFF_FACTOR`.

### Workspace context (AGENTS.md / SOUL.md / USER.md / PREFERENCES.md / skills / protocols)

`WORKSPACE_CONTEXT_ENABLED=true`,
`WORKSPACE_SKILLS_DIR_NAME=.agent/skills`,
`WORKSPACE_SETTINGS_FILENAME=.agent/protocols/permissions.md`.

### In-process `python` tool (opt-in, NOT sandboxed)

`VIRTUAL_PYTHON_ENABLED=false`, `VIRTUAL_PYTHON_TIMEOUT_SECONDS=30`,
`VIRTUAL_PYTHON_OUTPUT_CAP_BYTES=32000`. Single-tenant only — the
code can reach `os.environ`, `subprocess`, sockets.

### Chat rate limiting

`CHAT_RATE_LIMIT_PER_MINUTE=0` (off by default; pick a value for
public deploys).

### Cost tracking + audit log + redaction

`COST_TRACKER_ENABLED`, `COST_MAX_PER_REQUEST_USD`,
`COST_MAX_PER_USER_DAILY_USD`, `COST_RESET_WINDOW_HOURS`,
`AUDIT_LOG_ENABLED`, `AUDIT_LOG_RETENTION_DAYS`,
`SECRET_REDACTION_ENABLED`, `STRICT_CONVERSATION_READ_VALIDATION`.

### Ops platform

Scheduler: `SCHEDULER_ENABLED`, `SCHEDULER_PERSISTENT_JOBSTORE`.

### OAuth

Google: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
`GOOGLE_OAUTH_REDIRECT_URI`. Apple: `APPLE_OAUTH_CLIENT_ID`,
`APPLE_OAUTH_TEAM_ID`, `APPLE_OAUTH_KEY_ID`,
`APPLE_OAUTH_PRIVATE_KEY`, `APPLE_OAUTH_REDIRECT_URI`. Shared:
`OAUTH_POST_LOGIN_REDIRECT`.

### Telegram channel

`TELEGRAM_BOT_TOKEN` (empty = channel disabled),
`TELEGRAM_BOT_USERNAME`, `TELEGRAM_MODE` (`polling`/`webhook`),
`TELEGRAM_WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET`,
`TELEGRAM_VERBOSE_DEFAULT`, `TELEGRAM_TYPING_REFRESH_SECONDS`,
`TELEGRAM_USE_DRAFT_STREAMING`.

### Voice / STT

`VOICE_PROVIDER` (`xai` / `mistral` / `openai` / `local`),
`VOICE_MISTRAL_API_KEY`, `VOICE_OPENAI_API_KEY`,
`VOICE_WHISPER_CPP_BINARY`, `VOICE_WHISPER_CPP_MODEL`,
`VOICE_MAX_SIZE_MB`.

### Lossless Context Management (LCM)

`LCM_ENABLED`, `LCM_FRESH_TAIL_COUNT`, `LCM_LEAF_CHUNK_TOKENS`,
`LCM_CONTEXT_THRESHOLD`, `LCM_INCREMENTAL_MAX_DEPTH`,
`LCM_SUMMARY_MODEL`.

### Plugins (per-workspace BYOK)

Plugins declare their own env keys in `<plugin>/plugin.py`. They are
**not** read from the gateway `.env` — each workspace's encrypted
`.env` carries them and tools resolve via
`resolve_api_key(workspace_id, …)`.

| Plugin | Key | Notes |
|--------|-----|-------|
| Notion | `NOTION_API_KEY` | Single `ntn` tool that proxies arbitrary args to the Notion CLI subprocess. Get the key from https://www.notion.so/profile/integrations |

POST to `/api/v1/workspaces/{workspace_id}/env` to set these without
the UI.

### Observability (OpenTelemetry, read directly by the OTel SDK)

`OTEL_EXPORTER_OTLP_ENDPOINT` (setting this enables the whole stack
— leave unset for no-op), `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`,
`OTEL_SERVICE_NAME=pawrrtal-backend`, `OTEL_EXPORTER_OTLP_HEADERS`.

### Dev admin login

`ADMIN_EMAIL`, `ADMIN_PASSWORD` (seeded account for the dev login
shortcut; disabled when `ENV=prod`).

> **Per-workspace overrides.** Every provider key above also lives in
> the workspace's encrypted `.env` (Settings → Environment in the UI).
> Tools resolve in priority order: workspace key → gateway `.env` key.

`DATABASE_URL` is **overridden** by `docker-compose.yml` to point at the
bundled postgres service — you don't need to change it in `.env`.

## Production / Railway

For Railway or any other managed platform, set `DATABASE_URL` in your
environment to the platform's connection string (Railway injects it
automatically) and deploy the backend normally. `backend/railway.toml`
runs `alembic upgrade head && exec uvicorn …` on boot. Migrations are
serialised across rolling-deploy replicas by a Postgres advisory lock
in `alembic/env.py`.

Production users typically also attach a Railway volume mounted at
`/data/workspaces` so workspace contents (memory, skills, encrypted
`.env`) survive redeploys.

For VPS deploys with the Paw CLI Cloudflared profile, see
[`frontend/content/docs/handbook/deployment/vps-deploy.md`](../frontend/content/docs/handbook/deployment/vps-deploy.md).
