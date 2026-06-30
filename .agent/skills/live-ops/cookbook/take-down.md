# Take Down Pawrrtal

## Context

Use this when the user asks to stop Pawrrtal, disable the live service, free ports, or safely remove public exposure.

## Steps

### 1. Identify what owns the running app

```bash
cd /mnt/HC_Volume_105512717/deploy/pawrrtal
just paw doctor --json
systemctl status pawrrtal.service --no-pager || true
systemctl --user status pawrrtal-dev.service --no-pager || true
ss -ltnp '( sport = :8000 or sport = :3000 or sport = :53001 )'
```

The current Bun CLI slice does not own app processes. If root
`pawrrtal.service` is active, it owns production. If only the user
`pawrrtal-dev.service` is active, treat that as a dev-service fallback.

### 2. Stop the app gracefully

For a systemd-owned process:

```bash
systemctl stop pawrrtal.service || systemctl --user stop pawrrtal-dev.service
```

Only disable autostart when the user asks for a persistent takedown:

```bash
systemctl disable pawrrtal.service || systemctl --user disable pawrrtal-dev.service
```

### 3. Stop public exposure when requested

If the user wants the public URL down too:

```bash
systemctl status cloudflared --no-pager || true
systemctl status cloudflared@pawrrtal --no-pager || true
systemctl stop cloudflared || true
systemctl stop cloudflared@pawrrtal || true
```

Do not delete tunnel credentials manually unless explicitly asked and backed up.

### 4. Prove it is down

```bash
ss -ltnp '( sport = :8000 or sport = :3000 or sport = :53001 )'
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsSI http://127.0.0.1:3000 || curl -fsSI http://127.0.0.1:53001
```

For a full public takedown:

```bash
curl -sSI https://pawrrtal.octaviantocan.com | sed -n '1,30p'
```

Decide whether the desired public result is Cloudflare Access still protecting an unavailable origin, a Cloudflare origin error, or no tunnel route. State which one you verified.

### 5. Clean auxiliary resources

If any ephemeral GitHub runners were started during the operation, clean them and verify nothing remains:

```bash
scripts/ephemeral-self-hosted-runners.sh cleanup --tag <tag>
systemctl list-units --type=service --all 'pawrrtal-gha-*.service' --no-pager
pgrep -af 'Runner.Listener|Runner.Worker|ephemeral-self-hosted-runners'
```

Report remaining listeners, services, and public exposure state.
