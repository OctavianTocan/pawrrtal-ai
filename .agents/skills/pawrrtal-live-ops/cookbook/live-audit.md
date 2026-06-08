# Live Audit

## Context

Use this when you need to prove Pawrrtal is operationally live, identify what code is actually running, or check the public Cloudflared URL.

## Steps

### 1. Identify the live processes

```bash
ROOT=${PAWRRTAL_ROOT:-/mnt/HC_Volume_105512717/dev/pawrrtal}
cd "$ROOT"
systemctl --user status pawrrtal-dev.service --no-pager
ss -ltnp '( sport = :8000 or sport = :3000 or sport = :53001 )'
ps -eo pid,ppid,stat,etime,cmd | rg 'dev.ts|uvicorn|next-server|cloudflared'
```

Record the backend PID, frontend PID, service name, frontend port, backend port, and how long the processes have been running.

### 2. Prove the running checkout and commit

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
```

Then compare with the live process working directory:

```bash
readlink -f /proc/<backend-pid>/cwd
readlink -f /proc/<frontend-pid>/cwd
```

If the running checkout is not on the expected branch or commit, say that directly. Do not call the deployment current just because `main` is merged on GitHub.

### 3. Inspect live environment without leaking secrets

```bash
tr '\0' '\n' < /proc/<backend-pid>/environ \
  | rg '^(DATABASE_URL|PAWRRTAL_DEV_DATABASE_URL|TELEGRAM|GOOGLE_CHAT|BACKEND|FRONTEND|COOKIE|CORS|ENV)=' \
  | sed -E 's#(DATABASE_URL|PAWRRTAL_DEV_DATABASE_URL)=.*#\1=<redacted>#; s#(.*TOKEN.*)=.*#\1=<redacted>#; s#(.*SECRET.*)=.*#\1=<redacted>#; s#(.*PASSWORD.*)=.*#\1=<redacted>#; s#(.*KEY.*)=.*#\1=<redacted>#'
```

Use this to detect shell/service mismatch. If a Paw CLI command fails because it reads a different `DATABASE_URL`, the live process environment wins.

### 4. Check local origins

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsSI http://127.0.0.1:3000 || curl -fsSI http://127.0.0.1:53001
cd backend && uv run paw project status --json
```

`paw project status --json` may report `tracked=false` when systemd owns the service. That is not a failure if the health checks and process table prove the service is live.

### 5. Check Cloudflared public exposure

```bash
systemctl status cloudflared --no-pager || true
systemctl status cloudflared@pawrrtal --no-pager || true
cloudflared tunnel ingress validate --config /etc/cloudflared/pawrrtal.yml
curl -sSI https://pawrrtal.octaviantocan.com | sed -n '1,30p'
```

The public hostname should hit Cloudflare Access before raw app HTML. A direct unauthenticated app page is a deployment failure.

### 6. Check schema state when the app has runtime DB errors

If logs show `UndefinedColumn`, `UndefinedTable`, failed model queries, or migration mismatch, run Alembic against the live database. Capture the live URL into a shell variable without printing it:

```bash
BACKEND_PID=<backend-pid>
LIVE_DATABASE_URL="$(tr '\0' '\n' < /proc/$BACKEND_PID/environ | sed -n 's/^DATABASE_URL=//p' | head -1)"
cd backend
DATABASE_URL="$LIVE_DATABASE_URL" uv run alembic current
DATABASE_URL="$LIVE_DATABASE_URL" uv run alembic heads
DATABASE_URL="$LIVE_DATABASE_URL" uv run alembic upgrade head
```

Restart the backend after schema changes if the service uses reloaders or cached metadata.
