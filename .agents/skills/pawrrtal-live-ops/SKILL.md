---
name: pawrrtal-live-ops
description: Operate Pawrrtal as a live service: prove the running commit, local origins, Cloudflared public URL, database schema, Telegram channel, and shutdown state. Use when checking whether Pawrrtal is live, deployed, reachable, healthy, broken in Telegram, safe to restart, or safe to take down.
stages: [debug, deploy]
benefits-from: [paw, systematic-debugging, diagnose, cloudflared-tunnel-ops]
---

# Pawrrtal Live Ops

Use this skill when the question is about the real running Pawrrtal service, not just the code in the checkout. The rule is: live process, live environment, live logs, live HTTP checks, then code.

## How It Works

Treat the running service as authoritative. The local shell may be on the wrong branch, may have the wrong `DATABASE_URL`, or may run a different Paw CLI profile than the user-facing service.

## Cookbook

Read the relevant cookbook before acting:

| Task | Cookbook | Use When |
| --- | --- | --- |
| Live audit | [cookbook/live-audit.md](cookbook/live-audit.md) | Prove what is running and whether local/public origins are healthy. |
| Functional verification | [cookbook/verify.md](cookbook/verify.md) | Prove user-visible flows such as login, chat, providers, and frontend checks. |
| Telegram diagnosis | [cookbook/telegram.md](cookbook/telegram.md) | Telegram receives no reply, commands fail, polling/webhook is suspect, or bindings look wrong. |
| Shutdown | [cookbook/take-down.md](cookbook/take-down.md) | Stop Pawrrtal cleanly, disable it, or prove it is down. |

## Operating Rules

1. Do not trust memory. Inspect the live service state every time.
2. Do not print tokens, credential JSON, origin certs, database URLs, service tokens, or bot tokens.
3. Prefer `paw` for user-visible verification, but if `paw` fails before HTTP due local env drift, switch to live process logs and raw HTTP checks.
4. Compare the live process checkout and commit against the commit you think is deployed.
5. If the database schema is involved, run migrations against the live service database, not the shell default.
6. After starting self-hosted runners for CI or verification, clean them and prove no runner services or processes remain.

## Fast Triage

For most incidents, run these in order:

```bash
ROOT=${PAWRRTAL_ROOT:-/mnt/HC_Volume_105512717/dev/pawrrtal}
cd "$ROOT"
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
systemctl --user status pawrrtal-dev.service --no-pager
ss -ltnp '( sport = :8000 or sport = :3000 or sport = :53001 )'
curl -fsS http://127.0.0.1:8000/api/v1/health
```

If Telegram is the complaint, go directly to [cookbook/telegram.md](cookbook/telegram.md) after the service status and health check.
