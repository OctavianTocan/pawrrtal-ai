# Running Pawrrtal with Docker Compose

The `docker-compose.yml` at the repo root spins up PostgreSQL 16 and the
FastAPI backend together. The Next.js frontend is left out intentionally —
you run it with the normal dev server so hot-reload keeps working.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose plugin)
- A Google Gemini API key — everything else is optional

## Quick start

```bash
# 1. Clone the repo (use --recurse-submodules for vendored frontend packages)
git clone --recurse-submodules https://github.com/OctavianTocan/Pawrrtal-AI.git
cd pawrrtal

# Plain clone? Run: git submodule update --init --recursive

# 2. Copy the Docker environment template and fill in your API keys
cp backend/.env.docker backend/.env
$EDITOR backend/.env   # set GOOGLE_API_KEY at minimum

# 3. Build and start the stack
docker compose up --build
```

The backend will be live at **http://localhost:8000** and PostgreSQL will be
exposed at **localhost:5432** (credentials: `pawrrtal` / `nexus_dev`, database `pawrrtal`).

Database migrations run automatically on every backend start via
`alembic upgrade head` (with a retry loop in case postgres isn't
fully accepting connections right as the healthcheck passes) — no
manual step needed.

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
| `GOOGLE_API_KEY` | ✅ | Powers the default Gemini model |
| `AUTH_SECRET` | ✅ | JWT signing secret — generate with `openssl rand -hex 32` |
| `FERNET_KEY` | ✅ | Encryption key for stored API keys |
| `CLAUDE_CODE_OAUTH_TOKEN` | Optional | Needed only for `claude-*` models |
| `EXA_API_KEY` | Optional | Enables web search |
| `XAI_API_KEY` | Optional | Enables voice / STT input |
| `TELEGRAM_BOT_TOKEN` | Optional | Enables the Telegram channel |

`DATABASE_URL` is **overridden** by `docker-compose.yml` to point at the
bundled postgres service — you do not need to change it in `.env`.

## Production / Railway

For Railway or any other managed platform, set `DATABASE_URL` in your
environment to the platform's connection string (Railway injects it
automatically) and deploy the backend normally. The Docker setup is
local-dev only.
