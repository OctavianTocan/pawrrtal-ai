# Running Pawrrtal with Docker Compose

The repo ships four compose files:

| File | Stack | Use case |
|---|---|---|
| `docker-compose.yml` | Postgres 16 + FastAPI backend | Base — same services every overlay extends |
| `docker-compose.dev.yml` | + ports `5432`, `8000` published locally; source bind-mount + `uvicorn --reload` | Local dev where you run the Next.js frontend with hot-reload from your host |
| `docker-compose.prod.yml` | + Next.js service + nginx reverse proxy on `:80` + health checks + memory caps + log rotation | A production-shaped stack on a VPS (TLS terminated upstream by Tailscale Serve / Caddy / etc.) |
| `docker-compose.demo.yml` | + `DEMO_MODE=true`, low rate limits, no Telegram, ephemeral workspace, outbound network blocked at the tool layer | Public demo deployments |

The Next.js frontend is left out of the base/dev stacks intentionally —
you run it on the host so hot-reload keeps working.

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

The dev server starts at **http://localhost:3001** and points at the backend
on port 8000 by default.

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

| Variable | Required | Description |
|----------|----------|-------------|
| `AUTH_SECRET` | ✅ | JWT signing secret — generate with `openssl rand -hex 32` |
| `WORKSPACE_ENCRYPTION_KEY` | ✅ | Fernet key for per-workspace encrypted `.env` files (32 random bytes, base64-encoded) |
| `GOOGLE_API_KEY` | ⚠️ | Required if you want any Gemini model (default catalog entry uses one) |
| `CLAUDE_CODE_OAUTH_TOKEN` | ⚠️ | Required for `claude-*` models |
| `EXA_API_KEY` | Optional | Web search via `exa_search` |
| `XAI_API_KEY` | Optional | xAI Grok models + voice STT |
| `OPENAI_CODEX_OAUTH_TOKEN` | Optional | Image generation tool |
| `NOTION_API_KEY` | Optional | Activates the Notion plugin (18 tools via `ntn`) |
| `TELEGRAM_BOT_TOKEN` | Optional | Enables the Telegram channel |

At least one of `GOOGLE_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` is needed for the chat
endpoint to do anything useful. The "optional" provider keys are also overridable
**per workspace** via Settings → Environment (encrypted with `WORKSPACE_ENCRYPTION_KEY`);
the gateway-global values in `.env` act as the fallback.

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

For VPS deploys (Docker Compose prod overlay + nginx), see
[`frontend/content/docs/handbook/deployment/vps-deploy.md`](../frontend/content/docs/handbook/deployment/vps-deploy.md).
