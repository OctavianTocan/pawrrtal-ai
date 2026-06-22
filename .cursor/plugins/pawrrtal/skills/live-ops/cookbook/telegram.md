# Telegram Diagnosis

## Context

Use this when the Telegram bot does not reply, commands do nothing, link flow
fails, "connect your account" appears unexpectedly, or channel runtime state is
uncertain.

## Steps

### 0. Separate outbound proof from inbound proof

Do not treat a successful `sendMessage` call as proof that a user's Telegram
account is connected. Outbound delivery only proves the bot token can send to
that chat. A connected-account claim requires inbound proof:

1. The user sends a fresh message to the exact bot being tested.
2. The expected systemd unit logs the update.
3. The logged bot id matches the target's Telegram bot id.
4. The target database resolves the sender's Telegram user id through
   `channel_bindings`.

When prod and dev both run Telegram polling, build a matrix before diagnosing:

| Target | Unit | Expected proof |
| --- | --- | --- |
| prod | `pawrrtal.service` | update log shows prod bot id and prod DB resolves the sender |
| dev | `pawrrtal-dev.service` | update log shows dev bot id and dev DB resolves the sender |

If the user reports seeing "connect your account", first determine which bot
and unit sent that message. In a prod/dev split, the common failure is that prod
is correctly bound while the dev bot has its own empty database.

### 1. Prove whether Telegram reached the backend

Start with logs around the user attempt:

```bash
for unit in pawrrtal.service pawrrtal-dev.service; do
  echo "### $unit"
  journalctl -u "$unit" --since '20 minutes ago' --no-pager \
    | rg -i 'telegram|aiogram|bot id|update id|connect your account|poll|webhook|undefinedcolumn|error|traceback|exception|disabled' \
    | sed -E 's#(bot[0-9]+:)[A-Za-z0-9_-]+#\1<redacted>#g' \
    | tail -n 120 || true
done
```

If you see `Update id=... is not handled` or an exception after an update,
Telegram reached the bot and the failure is inside Pawrrtal. If only the dev
unit logs an update, do not diagnose prod binding state as the cause of that
reply.

### 2. Check Telegram runtime configuration

```bash
systemctl status pawrrtal.service --no-pager || systemctl --user status pawrrtal-dev.service --no-pager
ss -ltnp '( sport = :8000 or sport = :8100 )'
tr '\0' '\n' < /proc/<backend-pid>/environ \
  | rg '^(TELEGRAM|DATABASE_URL|PAWRRTAL_DEV_DATABASE_URL|PAWRRTAL_SERVICE_TARGET)=' \
  | sed -E 's#(DATABASE_URL|PAWRRTAL_DEV_DATABASE_URL)=.*#\1=<redacted>#; s#(.*TOKEN.*)=.*#\1=<redacted>#; s#(.*SECRET.*)=.*#\1=<redacted>#'
```

Confirm mode, token presence, simulation flag, service target, and whether the
live service uses the expected database.

### 3. Compare target bot identities without exposing tokens

Use the Bitwarden-backed service launcher helpers or the live service
environment to call Telegram `getMe` for each configured target. Print only
safe metadata: configured username, bot id, bot username, webhook URL presence,
and pending update count. Never print the token.

The proof you want is:

- prod and dev bot ids are distinct when both services are polling.
- the bot id in the journal line matches the bot the user actually messaged.
- webhook URL is empty in polling mode.

If prod and dev share the same bot id, stop and fix the secrets or disable one
poller before testing. Two services must not poll the same Telegram bot.

### 4. Prove the sender resolves in the target database

Check the target database that belongs to the unit that handled the update. The
handler uses the same shape as:

```python
await get_user_id_for_external(
    provider="telegram",
    external_user_id="<sender user id>",
    session=session,
)
```

Also inspect the default workspace row for that user. A binding without a
default workspace can still fail later in the Telegram flow.

For dev/prod parity requests, verify both targets independently. A prod binding
does not imply a dev binding because the databases are separate by design.

### 5. Run Paw diagnostics when the CLI environment is valid

```bash
cd backend
uv run paw channels diagnose-telegram --json
uv run paw verify telegram --json
```

If these commands fail before hitting HTTP because the shell has a broken
`DATABASE_URL`, do not stop there. Continue with live logs, live process
environment, and raw API checks.

### 6. Check Telegram API state without exposing the token

Only run this in a shell where `TELEGRAM_BOT_TOKEN` is already available. Do
not print the token.

```bash
curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" \
  | jq '{ok, result: {url: .result.url, pending_update_count: .result.pending_update_count, last_error_date: .result.last_error_date, last_error_message: .result.last_error_message}}'
```

For polling mode, webhook URL should normally be empty. For webhook mode, URL
and secret configuration must match the public route.

### 7. Check database schema if updates crash

The common hard failure is schema drift after code changes. If logs show a
missing column such as `conversations.channel_thread_key`, run live migrations:

```bash
BACKEND_PID=<backend-pid>
LIVE_DATABASE_URL="$(tr '\0' '\n' < /proc/$BACKEND_PID/environ | sed -n 's/^DATABASE_URL=//p' | head -1)"
cd backend
DATABASE_URL="$LIVE_DATABASE_URL" uv run alembic current
DATABASE_URL="$LIVE_DATABASE_URL" uv run alembic upgrade head
systemctl restart pawrrtal.service || systemctl --user restart pawrrtal-dev.service
```

Re-send a Telegram message after restart and re-read logs.

### 8. Use simulated Telegram for fast regression checks

When `TELEGRAM_SIMULATE_ENABLED=true`:

```bash
cd backend
uv run paw lab telegram chat --turns /tmp/telegram-turns.txt --new --verbose 2 --json
uv run paw lab flows show telegram-polish-loop
```

Simulation proves Pawrrtal's dispatcher path. A real Telegram message still
proves the external ingress path.

### 9. State the root cause

Use exact evidence:

- `No update in logs`: Telegram is not reaching this backend.
- `Update in logs plus exception`: Telegram reaches Pawrrtal; fix the backend exception.
- `Update in dev logs only`: the user messaged the dev bot; inspect the dev DB, not prod.
- `Bot id mismatch`: the user messaged a different bot than the target under test.
- `Binding missing in target DB`: seed/link that target; do not assume prod and dev share bindings.
- `Diagnostics say service not running`: lifecycle/config problem.
- `Webhook/polling mismatch`: Telegram delivery mode problem.
- `Missing DB column/table`: migration/deployment mismatch.

### 10. Minimum proof before saying Telegram is fixed

Report all of these:

- target name and systemd unit
- bot username and bot id, with no token
- journal line evidence that the fresh inbound update hit that unit
- database lookup result for `provider="telegram"` and the sender id
- default workspace path and whether it exists
- health/ready result for the target backend
