# Demo-mode deployment

Demo mode is a deployment **shape**, not a feature flag.  It wires
Pawrrtal into a configuration safe for an unattended public "try it
out" instance — separate billing pool, ephemeral state, restricted
tool surface, no Telegram.

This doc describes what demo mode is, how to deploy it, and the
explicit limits you trade off for the public-friendliness.

> **Status:** scaffold.  The compose overlay + config toggle exist.
> Frontend banner + demo-key bake-in + tool-allowlist enforcement
> are TODO (see "Open follow-ups" at the bottom).

## What demo mode promises

When `DEMO_MODE=true`:

- **No Telegram channel.**  Even with a valid `TELEGRAM_BOT_TOKEN` in
  the env, `telegram_lifespan` returns early before starting the bot.
  We never expose a Telegram surface in demo because the bot can talk
  to any user who messages it, blowing the per-user rate budget on
  bot-initiated traffic.
- **Open sign-up.**  `ALLOWED_EMAILS=""` so anyone can register and
  start a chat.  Cloudflare edge controls are what protect the public
  hostname from arbitrary request floods.
- **Hard rate cap.**  `CHAT_RATE_LIMIT_PER_MINUTE` is set low (15 by
  default in `docker-compose.demo.yml`).  One demo user can cost at
  most that many requests / minute.
- **Ephemeral workspace.**  `WORKSPACE_BASE_DIR=/data/demo-workspaces`
  on a Docker-managed volume that is NOT marked persistent in the
  overlay — `docker compose down` wipes it.  Demo users see a blank
  workspace on every fresh deploy.
- **Restricted tool surface.**  Web search (`EXA_API_KEY=""`) is
  forced off so a demo user can't run up Exa charges.  Image
  generation should be off too (`OPENAI_CODEX_OAUTH_TOKEN=""` —
  otherwise your personal Codex auth gets shared).

## What demo mode does NOT promise (yet)

These are listed so an operator knows what *isn't* covered by the
overlay and what they must do manually until follow-up PRs land:

- A visible **"DEMO" banner** in the frontend.  Today the only
  signal is configuration drift; a user can't tell from the UI that
  they're in demo mode.
- **Per-IP rate limiting on top of per-user.**  The current limit is
  per authenticated user, so a single attacker can grind through
  signups to bypass.  Cloudflare in front is the recommended
  stopgap.
- **Token usage caps per deploy.**  Rate limiting bounds requests
  per minute but not total tokens spent in a day.  Set a hard ceiling
  on your provider account dashboard.
- **Tool allowlist enforcement.**  Right now the agent's tool list
  is composed from settings; demo mode is configured by clearing the
  relevant env vars.  A proper allowlist that refuses to attach
  certain tools regardless of config is a follow-up.

## How to deploy

The overlay sits next to the existing `docker-compose.yml` and is
applied with `-f`:

```bash
# On the VPS, from the repo root:
cp backend/.env.docker.example backend/.env
$EDITOR backend/.env  # fill in the demo-specific keys (see below)

docker compose -f docker-compose.yml -f docker-compose.demo.yml up --build
```

The overlay:

- Switches to a separate `postgres_demo_data` volume so demo state
  doesn't bleed into your private deploy.
- Mounts a separate `demo_workspace_data` volume that's ephemeral
  across container recreation.
- Forces the env vars listed above on the backend service.

### `backend/.env` for a demo deploy

```env
# ── Required ─────────────────────────────────────────────────────
SECRET_KEY=...                       # JWT signing
AUTH_SECRET=...                      # FastAPI-Users password reset
WORKSPACE_ENCRYPTION_KEY=...         # Fernet key (cryptography.fernet.Fernet.generate_key())

# ── LLM provider — pick ONE, scoped to a demo billing pool ──────
GOOGLE_API_KEY=...                   # cheapest path; use a key on a separate billing account
# CLAUDE_CODE_OAUTH_TOKEN=          # leave empty for demo unless you accept the cost

# ── Demo-mode overlay handles these; DON'T override here ────────
# DEMO_MODE=true                     # set by docker-compose.demo.yml
# ALLOWED_EMAILS=                    # forced empty by overlay
# CHAT_RATE_LIMIT_PER_MINUTE=15      # forced by overlay
# TELEGRAM_BOT_TOKEN=                # forced empty by overlay
# EXA_API_KEY=                       # forced empty by overlay
# WORKSPACE_BASE_DIR=/data/demo-workspaces  # forced by overlay

# ── Optional ────────────────────────────────────────────────────
GOOGLE_OAUTH_CLIENT_ID=...           # if you want demo users to sign in with Google
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=https://demo.pawrrtal.ai/api/v1/auth/oauth/google/callback
```

### Frontend build

The frontend uses same-origin browser API calls. Build it normally and
publish it through the same Cloudflared hostname as the backend paths:

```bash
cd frontend
bun run build
```

Do not bake backend shared secrets into public frontend bundles.

## Recommended infra

- Separate VPS from your private deploy if possible.  At minimum, a
  separate Postgres database and a separate workspace volume (the
  overlay handles both).
- Cloudflare in front, with Bot Fight Mode + per-IP rate limit at
  the edge (10 req / 10 s is a reasonable starting point for the
  whole demo origin).
- Separate provider billing pool — a Google Cloud project /
  Anthropic workspace dedicated to demo with a hard monthly budget.
- A daily `docker compose down && docker compose ... up` to wipe
  state.  Demo conversations should not survive overnight.

## Operating tips

- Watch the `RATE_LIMIT` log lines from `ChatRateLimitMiddleware` —
  they're your earliest signal that an attacker is grinding the
  demo.
- If demo gets abused, bump `CHAT_RATE_LIMIT_PER_MINUTE` down to 5
  and add Cloudflare's "I'm Under Attack" mode without redeploying.
- Cloudflare is your public kill switch. Tighten Access/WAF policies or
  enable "I'm Under Attack" mode without taking the backend down.

## Open follow-ups

- [ ] Frontend "DEMO MODE" banner driven by a `/api/v1/health/ready`
      response field.
- [ ] Tool allowlist enforced inside `build_agent_tools` regardless of
      env-var presence (defense in depth).
- [ ] Per-IP rate limiting layer in addition to per-user.
- [ ] Daily cron inside the backend container that wipes
      `chat_messages` rows older than 24 h.
- [ ] Auto-archive the demo Postgres database nightly + restore from
      empty so even users who don't trigger a `compose down` get a
      fresh slate.
