# Telegram Diagnosis

## Context

Use this when the Telegram bot does not reply, commands do nothing, link flow fails, or channel runtime state is uncertain.

## Steps

### 1. Prove whether Telegram reached the backend

Start with logs around the user attempt:

```bash
journalctl --user -u pawrrtal-dev.service --since '20 minutes ago' --no-pager \
  | rg -i 'telegram|aiogram|bot id|update id|poll|webhook|undefinedcolumn|error|traceback|exception|disabled'
```

If you see `Update id=... is not handled` or an exception after an update, Telegram reached the bot and the failure is inside Pawrrtal.

### 2. Check Telegram runtime configuration

```bash
systemctl --user status pawrrtal-dev.service --no-pager
ss -ltnp '( sport = :8000 )'
tr '\0' '\n' < /proc/<backend-pid>/environ \
  | rg '^(TELEGRAM|DATABASE_URL|PAWRRTAL_DEV_DATABASE_URL)=' \
  | sed -E 's#(DATABASE_URL|PAWRRTAL_DEV_DATABASE_URL)=.*#\1=<redacted>#; s#(.*TOKEN.*)=.*#\1=<redacted>#; s#(.*SECRET.*)=.*#\1=<redacted>#'
```

Confirm mode, token presence, simulation flag, and whether the live service uses the expected database.

### 3. Run Paw diagnostics when the CLI environment is valid

```bash
cd backend
uv run paw channels diagnose-telegram --json
uv run paw verify telegram --json
```

If these commands fail before hitting HTTP because the shell has a broken `DATABASE_URL`, do not stop there. Continue with live logs, live process environment, and raw API checks.

### 4. Check Telegram API state without exposing the token

Only run this in a shell where `TELEGRAM_BOT_TOKEN` is already available. Do not print the token.

```bash
curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" \
  | jq '{ok, result: {url: .result.url, pending_update_count: .result.pending_update_count, last_error_date: .result.last_error_date, last_error_message: .result.last_error_message}}'
```

For polling mode, webhook URL should normally be empty. For webhook mode, URL and secret configuration must match the public route.

### 5. Check database schema if updates crash

The common hard failure is schema drift after code changes. If logs show a missing column such as `conversations.channel_thread_key`, run live migrations:

```bash
BACKEND_PID=<backend-pid>
LIVE_DATABASE_URL="$(tr '\0' '\n' < /proc/$BACKEND_PID/environ | sed -n 's/^DATABASE_URL=//p' | head -1)"
cd backend
DATABASE_URL="$LIVE_DATABASE_URL" uv run alembic current
DATABASE_URL="$LIVE_DATABASE_URL" uv run alembic upgrade head
systemctl --user restart pawrrtal-dev.service
```

Re-send a Telegram message after restart and re-read logs.

### 6. Use simulated Telegram for fast regression checks

When `TELEGRAM_SIMULATE_ENABLED=true`:

```bash
cd backend
uv run paw lab telegram chat --turns /tmp/telegram-turns.txt --new --verbose 2 --json
uv run paw lab flows show telegram-polish-loop
```

Simulation proves Pawrrtal's dispatcher path. A real Telegram message still proves the external ingress path.

### 7. State the root cause

Use exact evidence:

- `No update in logs`: Telegram is not reaching this backend.
- `Update in logs plus exception`: Telegram reaches Pawrrtal; fix the backend exception.
- `Diagnostics say service not running`: lifecycle/config problem.
- `Webhook/polling mismatch`: Telegram delivery mode problem.
- `Missing DB column/table`: migration/deployment mismatch.
