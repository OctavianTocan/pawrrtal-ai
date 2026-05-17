---
title: Deploying Pawrrtal on a VPS — step by step
description: Canonical operator runbook for standing up a private Pawrrtal instance on a VPS.
---

# Deploying Pawrrtal on a VPS — step by step

This guide is the **canonical operator runbook** for standing up a
private Pawrrtal instance for you and a small number of allowlisted
users.  It assumes:

- A VPS with Docker + Docker Compose installed (Hetzner, DO, Linode,
  Vultr — any will do).  2 vCPU / 4 GB RAM is the floor; 4 vCPU /
  8 GB is comfortable.
- A domain name you control.
- SSH access to the VPS as a non-root user with `docker` group
  membership.
- ~2 hours of focused time.

Sections marked **REQUIRED** must be completed before you point real
users at the deploy.  Sections marked **OPTIONAL** are recommended
hardening you can defer.

---

## Table of contents

1. [Prerequisites & assumptions](#1-prerequisites--assumptions)
2. [Clone the repo + branch hygiene](#2-clone-the-repo--branch-hygiene)
3. [Generate every secret you need](#3-generate-every-secret-you-need-required)
4. [Configure `backend/.env`](#4-configure-backendenv-required)
5. [Set up the reverse proxy + TLS](#5-set-up-the-reverse-proxy--tls-required)
6. [DNS](#6-dns-required)
7. [First boot](#7-first-boot-required)
8. [Configure Google OAuth](#8-configure-google-oauth-optional-but-recommended)
9. [Telegram channel](#9-telegram-channel-optional)
10. [Backups](#10-backups-skip)
11. [Monitoring — OpenTelemetry traces](#11-monitoring--opentelemetry-traces-required)
12. [Updating](#12-updating)
13. [Disaster recovery](#13-disaster-recovery)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Prerequisites & assumptions

```bash
# On the VPS, confirm the stack:
docker --version          # 24+
docker compose version    # v2.x (the new plugin, not docker-compose)
git --version
```

If Docker isn't installed, follow the official Docker convenience
script (`get.docker.com`) and add your user to the `docker` group.

This guide assumes **PRs #173 (Nginx + frontend Dockerfile), #174
(BACKEND_API_KEY + allowlist), #175 (preferences TOML), #176
(Conversation.updated_at fix + integrations cleanup), #179
(get_allowed_user wiring + readiness probe), #180 (rate limiting)**
are all merged to `development`.  If any are still open, merge them
before running through this guide or you'll hit gaps.

## 2. Clone the repo + branch hygiene

```bash
cd /opt
sudo git clone https://github.com/OctavianTocan/Pawrrtal-AI.git pawrrtal
sudo chown -R $USER:$USER pawrrtal
cd pawrrtal

# Use a stable release branch in production, not `development`.
# Tag the version you're deploying so a rollback knows what to
# return to.
git checkout development        # or your release tag
git submodule update --init --recursive
```

## 3. Generate every secret you need (REQUIRED)

Pawrrtal needs **five** secrets, all of which must be high-entropy
random values you generate fresh.  Never re-use values from another
service.

```bash
# 1. JWT signing key for auth cookies
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"

# 2. FastAPI-Users password-reset/verification secret
python3 -c "import secrets; print('AUTH_SECRET=' + secrets.token_urlsafe(64))"

# 3. Transport-layer backend API key.  Bake the SAME value into
# the frontend at build time as NEXT_PUBLIC_BACKEND_API_KEY.
python3 -c "import secrets; print('BACKEND_API_KEY=' + secrets.token_urlsafe(48))"

# 4. Workspace .env Fernet key (per-user encrypted env overrides)
python3 -c "from cryptography.fernet import Fernet; print('WORKSPACE_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# 5. Postgres password
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
```

Save the output somewhere safe (1Password / Bitwarden).  These
values cannot be rotated without invalidating every session and
re-encrypting every workspace env file, so treat them as durable.

## 4. Configure `backend/.env` (REQUIRED)

```bash
cp backend/.env.docker.example backend/.env
$EDITOR backend/.env
```

Fill it in.  Annotated template:

```bash
# ── Core ─────────────────────────────────────────────────────────
ENV=prod                                  # cookies become secure-only
DATABASE_URL=postgresql://pawrrtal:<POSTGRES_PASSWORD>@postgres:5432/pawrrtal
AUTH_SECRET=<from step 3>
BACKEND_API_KEY=<from step 3>             # X-Pawrrtal-Key header gate
WORKSPACE_ENCRYPTION_KEY=<from step 3>    # Fernet
WORKSPACE_BASE_DIR=/data/workspaces

# ── Identity gate (REQUIRED for private deploy) ──────────────────
# Comma-separated emails allowed to use this instance.
# Anyone else who signs in gets 403 on every protected route.
ALLOWED_EMAILS=tocanoctavian@gmail.com,esther@example.com

# ── Rate limiting ────────────────────────────────────────────────
# Caps chat requests per user per minute.  Pick a value that matches
# your monthly token budget divided by expected request count.
# 0 = unlimited (only for local dev — never in prod).
CHAT_RATE_LIMIT_PER_MINUTE=30

# ── CORS ─────────────────────────────────────────────────────────
# Comma-separated list of origins your frontend will hit the API from.
CORS_ORIGINS=["https://pawrrtal.your-domain.com"]
# Optional regex applied in addition to the list — handy for Vercel
# previews where the subdomain changes per deploy.
# CORS_ORIGIN_REGEX=^https:\/\/.*\.vercel\.app$

# ── Cookies ──────────────────────────────────────────────────────
COOKIE_DOMAIN=.your-domain.com            # share session across www + bare
COOKIE_SECURE=true
COOKIE_SAMESITE=lax

# ── LLM providers (need at least one) ────────────────────────────
GOOGLE_API_KEY=...
CLAUDE_CODE_OAUTH_TOKEN=...               # optional — generate via `claude setup-token`

# ── Optional providers ───────────────────────────────────────────
EXA_API_KEY=...                           # web search; leave blank to disable
XAI_API_KEY=...                           # voice/STT proxy; leave blank to disable

# ── Postgres ─────────────────────────────────────────────────────
POSTGRES_USER=pawrrtal
POSTGRES_PASSWORD=<from step 3>
POSTGRES_DB=pawrrtal

# ── Telegram (optional — see section 9) ──────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_MODE=polling                     # webhook needs a public URL
TELEGRAM_WEBHOOK_URL=
TELEGRAM_WEBHOOK_SECRET=
# TELEGRAM_VERBOSE_DEFAULT=1              # 0=quiet, 1=tools, 2=+thinking
# TELEGRAM_TYPING_REFRESH_SECONDS=2.5     # typing indicator refresh cadence
# TELEGRAM_USE_DRAFT_STREAMING=false      # Bot API 9.3+ animated streaming

# ── OAuth (optional — see section 8) ─────────────────────────────
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=https://pawrrtal.your-domain.com/api/v1/auth/oauth/google/callback
APPLE_OAUTH_CLIENT_ID=
APPLE_OAUTH_TEAM_ID=
APPLE_OAUTH_KEY_ID=
APPLE_OAUTH_PRIVATE_KEY=
APPLE_OAUTH_REDIRECT_URI=
OAUTH_POST_LOGIN_REDIRECT=https://pawrrtal.your-domain.com/

# ── Hardening + opt-in features (defaults are sensible; tune as needed)
#
# Cost / budget enforcement (forwarded to Claude SDK; mirrored in Gemini loop):
COST_TRACKER_ENABLED=true
COST_MAX_PER_REQUEST_USD=1.0
COST_MAX_PER_USER_DAILY_USD=10.0
COST_RESET_WINDOW_HOURS=24
#
# Audit log retention:
AUDIT_LOG_ENABLED=true
AUDIT_LOG_RETENTION_DAYS=90
SECRET_REDACTION_ENABLED=true
#
# Agent safety caps (empty string disables a guard):
AGENT_MAX_ITERATIONS=25
AGENT_MAX_WALL_CLOCK_SECONDS=300
AGENT_MAX_CONSECUTIVE_LLM_ERRORS=3
AGENT_MAX_CONSECUTIVE_TOOL_ERRORS=5
AGENT_LLM_RETRY_BACKOFF_SECONDS=1.0
#
# Claude SDK macOS Seatbelt sandbox (off — opt-in only):
CLAUDE_SANDBOX_ENABLED=false
CLAUDE_SANDBOX_AUTO_ALLOW_BASH=true
CLAUDE_SANDBOX_EXCLUDED_COMMANDS=sudo,ssh,scp,rsync
#
# Claude SDK retry-with-backoff (caps transient-error retry):
CLAUDE_RETRY_MAX_ATTEMPTS=3
CLAUDE_RETRY_BASE_DELAY_SECONDS=1.0
CLAUDE_RETRY_MAX_DELAY_SECONDS=30.0
CLAUDE_RETRY_BACKOFF_FACTOR=2.0
#
# Workspace context assembly (CLAUDE.md/AGENTS.md/SOUL.md + skills):
WORKSPACE_CONTEXT_ENABLED=true
WORKSPACE_SKILLS_DIR_NAME=.claude/skills
WORKSPACE_SETTINGS_FILENAME=.claude/settings.json
#
# In-process `python` agent tool — single-tenant only, NOT sandboxed:
VIRTUAL_PYTHON_ENABLED=false
VIRTUAL_PYTHON_TIMEOUT_SECONDS=30
VIRTUAL_PYTHON_OUTPUT_CAP_BYTES=32000
#
# LCM (lossless context management). Off by default; on if you expect
# long sessions or chat surfaces with short, dense messages (Telegram).
LCM_ENABLED=false
LCM_FRESH_TAIL_COUNT=64
LCM_LEAF_CHUNK_TOKENS=20000
LCM_CONTEXT_THRESHOLD=0.75
LCM_INCREMENTAL_MAX_DEPTH=1
# LCM_SUMMARY_MODEL=                      # empty = same model as conversation
#
# Webhooks (ingest CI events, external triggers — opt-in):
WEBHOOK_API_ENABLED=false
WEBHOOK_API_SECRET=
GITHUB_WEBHOOK_SECRET=
#
# Scheduler (APScheduler — drives audit-purge job + future jobs):
SCHEDULER_ENABLED=false
SCHEDULER_PERSISTENT_JOBSTORE=true
#
# Voice / STT (xai is the default; mistral/openai/local are alternates):
VOICE_PROVIDER=xai
# VOICE_MISTRAL_API_KEY=
# VOICE_OPENAI_API_KEY=
# VOICE_WHISPER_CPP_BINARY=               # auto-detected from PATH when empty
# VOICE_WHISPER_CPP_MODEL=base
VOICE_MAX_SIZE_MB=25
#
# Strict mode for the ConversationRead schema (422 on non-canonical
# stored model_id). Set false as an escape hatch — bad rows fall back
# to the catalog default and are logged.
STRICT_CONVERSATION_READ_VALIDATION=true
#
# Public-demo lockdown — refuses to start the Telegram channel and
# enforces the demo restrictions in docs/deployment/demo-mode.md.
DEMO_MODE=false
```

Every variable above maps to a field on
[`backend/app/core/config.py::Settings`](https://github.com/OctavianTocan/pawrrtal/blob/development/backend/app/core/config.py).
The full reference template (with every field commented) lives at
[`backend/.env.example`](https://github.com/OctavianTocan/pawrrtal/blob/development/backend/.env.example).

Then update `docker-compose.yml`'s postgres service to read
`POSTGRES_PASSWORD` from `.env` instead of the hardcoded
`pawrrtal_dev`:

```yaml
postgres:
  environment:
    POSTGRES_USER: ${POSTGRES_USER}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    POSTGRES_DB: ${POSTGRES_DB}
```

…or set `POSTGRES_PASSWORD=pawrrtal_dev` in `.env` to keep the
compose file unchanged (NOT recommended for prod).

## 5. Set up the reverse proxy + TLS (REQUIRED)

You have three reasonable options.  Pick one:

### Option A: Caddy in front of Docker Compose (recommended)

Simplest path.  Caddy auto-provisions Let's Encrypt certs.

```bash
sudo apt install -y caddy
sudo tee /etc/caddy/Caddyfile > /dev/null <<'EOF'
pawrrtal.your-domain.com {
    encode gzip
    reverse_proxy /api/* localhost:8000
    reverse_proxy /auth/* localhost:8000
    reverse_proxy /users/* localhost:8000
    reverse_proxy * localhost:3000
}
EOF
sudo systemctl restart caddy
```

The backend listens on `:8000`, frontend on `:3000` — both bound to
`127.0.0.1` in your `docker-compose.yml`.  Caddy handles TLS + HTTP/2.

### Option B: Nginx (using PR #173's overlay)

If PR #173 is merged, you have a production compose file with an
Nginx service baked in.  Edit the `.conf` to point at your domain,
then run `certbot --nginx -d pawrrtal.your-domain.com`.

### Option C: Cloudflare Tunnel

If you want to avoid opening ports on the VPS at all:

```bash
cloudflared tunnel create pawrrtal
cloudflared tunnel route dns pawrrtal pawrrtal.your-domain.com
# edit ~/.cloudflared/config.yml to route to localhost:3000 + :8000
cloudflared tunnel run pawrrtal
```

Cloudflare also handles TLS + DDoS in front automatically.

**SSE compatibility:** whichever you pick, ensure proxy buffering is
**off** for the API paths.  Caddy is fine by default.  Nginx needs
`proxy_buffering off`.  Cloudflare needs you to either disable proxy
("grey cloud") for the API subdomain or use a Cloudflare Worker
configured for streaming responses.

## 6. DNS (REQUIRED)

Point an `A` record (`pawrrtal.your-domain.com` → VPS IP) and wait
for propagation (`dig +short pawrrtal.your-domain.com`).  If using
Cloudflare Tunnel, the tunnel command above does this for you.

## 7. First boot (REQUIRED)

```bash
cd /opt/pawrrtal
docker compose up --build -d
docker compose logs -f backend
```

Watch for:

```
[docker-compose] alembic upgrade head
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

Then verify the readiness probe:

```bash
curl https://pawrrtal.your-domain.com/api/v1/health
# {"status":"ok"}

curl https://pawrrtal.your-domain.com/api/v1/health/ready
# {"status":"ready","checks":{"database":{"ok":true,...},"providers":{"ok":true,"configured":["google"],...}}}
```

If `/health/ready` returns 503, the body lists exactly which check
failed.  Most common: no provider key configured.

Open the frontend URL in a browser.  Sign up with one of the emails
in `ALLOWED_EMAILS`.  Send a chat message.  If you get a reply, you
have a working deploy.

## 8. Configure Google OAuth (OPTIONAL but recommended)

Without OAuth, users have to sign up with email + password — which
works but is slower.

1. Go to https://console.cloud.google.com → APIs & Services → Credentials.
2. Create an **OAuth 2.0 Client ID** of type **Web application**.
3. Authorized redirect URI:
   `https://pawrrtal.your-domain.com/api/v1/auth/oauth/google/callback`
4. Copy the client ID + secret into `backend/.env` and restart:
   ```bash
   docker compose restart backend
   ```

The OAuth start route is `/api/v1/auth/oauth/google/start` — that's
what the frontend's "Sign in with Google" button hits.

Apple OAuth is **not yet implemented** (the callback returns 501).
Hold off until that lands.

## 9. Telegram channel (OPTIONAL)

1. Create a bot via [@BotFather](https://t.me/BotFather), get a token.
2. Note the bot username (without the leading `@`).
3. In `backend/.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=<from BotFather>
   TELEGRAM_BOT_USERNAME=<bot username>
   TELEGRAM_MODE=polling
   ```
4. Restart backend: `docker compose restart backend`.
5. Watch logs for `TELEGRAM_BOOT mode=polling`.
6. On the web app, open Settings → Channels → Connect Telegram, copy
   the 8-character code, and send it to your bot (or tap the deep
   link).  Bot responds `Connected ✅` and you can now chat from
   Telegram.

For webhook mode (preferred for prod — uses fewer resources):

```bash
TELEGRAM_MODE=webhook
TELEGRAM_WEBHOOK_URL=https://pawrrtal.your-domain.com/api/v1/telegram/webhook
TELEGRAM_WEBHOOK_SECRET=<generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
```

## 10. Backups (SKIP)

Tavi has explicitly opted out of automated backups for the current
deploy shape.  Conversations and workspace files live in their
respective Docker volumes (`postgres_data`, `workspace_data`).  If
those disappear, the deploy starts over from empty.  Accept the risk
or revisit this section later — don't half-build it.

## 11. Monitoring — OpenTelemetry traces (REQUIRED)

Pawrrtal emits OpenTelemetry traces for every HTTP request,
SQLAlchemy query, and outbound httpx call (Claude / Gemini / Codex /
Telegram / OAuth providers).  Enabling tracing is a one-env-var swap.

### Pick a backend

Any OTLP/HTTP-compatible backend works.  Common picks:

- **Grafana Cloud** — generous free tier, OTel-native.  Sign up at
  grafana.com, create an OTel connection, copy the endpoint + auth
  header.  Same backend PR #155's Sigil instrumentation publishes to.
- **Honeycomb** — best UX for slow-request triage.  Free tier covers
  a small private deploy comfortably.
- **Self-hosted Jaeger / Tempo / SigNoz** — if you don't want a
  third-party in the path.  Stand it up as another Docker service.

### Configure

Add to `backend/.env`:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-eu-west-2.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64-of-instance:token>
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_SERVICE_NAME=pawrrtal-backend
```

`OTEL_EXPORTER_OTLP_HEADERS` value is URL-encoded comma-separated
`key=value` pairs.  Most vendors give you the exact string to paste.

Restart the backend:

```bash
docker compose restart backend
docker compose logs backend | grep TELEMETRY_ENABLED
# TELEMETRY_ENABLED service=pawrrtal-backend endpoint=https://otlp-gateway-...
```

### What you'll see

Every chat request produces a trace tree like:

```
POST /api/v1/chat/                       (FastAPI span, ~3.4 s)
├─ SELECT conversations ...               (SQLAlchemy span, 4 ms)
├─ INSERT chat_messages ...               (SQLAlchemy span, 6 ms)
├─ POST anthropic.com/v1/messages         (httpx span, 3.1 s)
│  └─ stream chunks (provider-internal)
└─ UPDATE chat_messages SET content=...   (SQLAlchemy span, 5 ms)
```

The FastAPI root span carries semantic attributes set in the chat
router: `pawrrtal.user_id`, `pawrrtal.conversation_id`,
`pawrrtal.model_id`, `pawrrtal.surface`, `pawrrtal.question_len`,
`pawrrtal.request_id`.  Search by any of those to find the trace for
a specific user / conversation / model.

Log lines are auto-correlated: every `logger.info(...)` call inside
a traced request gets the `trace_id` + `span_id` injected so the
backend can join traces to logs in one view.

### Liveness / readiness still useful

Tracing covers per-request observability but doesn't replace simple
uptime probes.  Set up either:

- Uptime Robot / Better Stack hitting `/api/v1/health` every minute
  (liveness) + `/api/v1/health/ready` every 5 minutes (alerts when a
  provider key expires / DB dies).
- Or alerts directly off the OTel backend (Grafana / Honeycomb both
  support "trace count for `error_code != 0` over 5 min" rules).

PR #155 layers AI-provider-specific Sigil instrumentation on top of
the same OTel TracerProvider — once merged, you also get per-token
generations + cost in the same trace view.  Optional for a Tier 1
deploy.

## 12. Updating

```bash
cd /opt/pawrrtal
git fetch
git checkout <new tag>          # or git pull origin development
git submodule update --recursive
docker compose pull             # if you're using prebuilt images
docker compose up --build -d
docker compose logs -f backend  # watch for alembic upgrade head completing
```

Alembic migrations run automatically on every backend boot.  If a
migration fails, the backend won't start; check logs and roll back to
the previous tag if needed (see § 13).

## 13. Disaster recovery

### "I broke a migration, the backend won't start"

```bash
# 1. Roll back the code
git checkout <previous tag>
# 2. Roll back the schema
docker compose run --rm backend alembic downgrade -1
# 3. Boot
docker compose up --build -d
```

### "The Postgres volume is corrupt / gone"

```bash
# 1. Stop everything
docker compose down
# 2. Wipe the broken volume
docker volume rm pawrrtal_postgres_data
# 3. Restore the latest dump
docker volume create pawrrtal_postgres_data
docker compose up -d postgres
sleep 10
zcat /var/backups/pawrrtal/postgres_<latest>.sql.gz | \
    docker compose exec -T postgres psql -U pawrrtal -d pawrrtal
# 4. Boot the rest
docker compose up -d
```

### "The workspace volume is corrupt / gone"

```bash
docker compose down
docker volume rm pawrrtal_workspace_data
docker volume create pawrrtal_workspace_data
docker run --rm -v pawrrtal_workspace_data:/data \
    -v /var/backups/pawrrtal:/backup alpine \
    tar xzf "/backup/workspace_<latest>.tar.gz" -C /data
docker compose up -d
```

### "Everything is gone"

Provision a fresh VPS, follow this guide from § 2, restore both
volumes per § 13.  Sessions are invalidated (users have to log in
again) but conversations + files + bindings are preserved.

## 14. Troubleshooting

### Frontend says "Failed to fetch" on every request

- Check `BACKEND_API_KEY` env var on the backend matches the
  `NEXT_PUBLIC_BACKEND_API_KEY` baked into the frontend build.  If
  they don't match, every request returns 401 from the middleware.
- Check `CORS_ORIGINS` in `backend/.env` includes the frontend's
  exact origin (scheme + host + port).

### Chat replies don't stream — they appear all at once

- Caddy: should work out of the box. If not, ensure no
  `flush_interval` overrides.
- Nginx: add `proxy_buffering off;` + `proxy_cache off;` to the
  `/api/` location.
- Cloudflare: enable streaming on the worker or set the API
  subdomain to "DNS only" (grey cloud).

### `403 This Pawrrtal deployment is private.` on every protected route

You're authenticated but your email isn't in `ALLOWED_EMAILS`.  Edit
`backend/.env`, add the address, restart backend.

### `503 not-ready` from `/api/v1/health/ready`

The body tells you which check failed.  Most common:
- `providers.configured: []` → no LLM provider key set
- `database.detail: ...` → Postgres unreachable; check `docker compose ps postgres`

### Telegram bot doesn't respond

Check `docker compose logs backend | grep TELEGRAM`.  Most common
cause: webhook mode set but no public URL configured.  Switch to
polling for debugging.

### Costs exploding

- Hit Cloudflare's per-IP rate limit (10 req / 10 s is a good
  starting point).
- Lower `CHAT_RATE_LIMIT_PER_MINUTE`.
- Rotate `BACKEND_API_KEY` to kick everyone out, investigate, then
  rebuild frontend with the new key.

## What you, the operator, still own

Even with this guide, you make these decisions:

- Which VPS provider (cost vs reliability tradeoff).
- Which provider billing pool (one key per deploy isolates blast
  radius).
- Whether to put Cloudflare in front (recommended).
- How aggressive to set rate limits (depends on your budget).
- Backup destination (S3 / Backblaze / Hetzner Box / etc).
- When to apply updates (recommend test-on-staging-VPS-first if you
  have users).

The code can't make those calls for you.

---

## Appendix: minimum viable private deploy checklist

If you've done all of these, you have a working Tier 1 private
deploy:

- [ ] PRs #173, #174, #175, #176, #179, #180 merged to `development`
- [ ] VPS provisioned, Docker + Compose installed
- [ ] Domain DNS pointing at VPS
- [ ] All 5 secrets generated and stored in 1Password
- [ ] `backend/.env` filled in including `ALLOWED_EMAILS` + at least one provider key
- [ ] Caddy / Nginx / Cloudflare Tunnel terminating TLS on the public URL
- [ ] `docker compose up -d` boots cleanly
- [ ] `/api/v1/health/ready` returns 200 with all checks green
- [ ] One signup → one chat message → AI reply round-trip works
- [ ] `OTEL_EXPORTER_OTLP_ENDPOINT` + auth headers set, trace visible in your backend
- [ ] Uptime Robot / equivalent monitoring `/health` every minute

When all 10 boxes are checked, point Esther at the URL.
