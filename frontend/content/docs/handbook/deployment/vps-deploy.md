---
title: Deploying Pawrrtal on a VPS with Cloudflared
description: Canonical operator runbook for a Cloudflare Access protected Pawrrtal VPS.
---

# Deploying Pawrrtal on a VPS with Cloudflared

This is the canonical deployment shape for a private Pawrrtal VPS:

```text
Browser -> https://<pawrrtal-hostname>
Cloudflare Access -> Cloudflared named tunnel
Cloudflared -> 127.0.0.1:3000 for frontend pages
Cloudflared -> 127.0.0.1:8000 for /api/v1, /auth, /users
```

Local development stays plain localhost:

```text
Frontend: http://localhost:3000
Backend:  http://127.0.0.1:8000
```

There is no public Nginx, no Tailscale Serve profile, and no browser
backend URL picker. Browser API calls are same-origin. Server-side
Next.js calls use `BACKEND_INTERNAL_URL`, defaulting to
`http://127.0.0.1:8000`.

## Prerequisites

- A VPS with this repo checked out.
- `just install` has completed.
- `cloudflared` is installed on the VPS.
- The Cloudflare zone contains the public hostname, for example
  `pawrrtal.octaviantocan.com`.
- A Cloudflare Access application exists for that hostname.

Use Cloudflare's docs as the operational reference for named tunnels,
local config files, Linux services, and Access:

- https://developers.cloudflare.com/tunnel/advanced/local-management/configuration-file/
- https://developers.cloudflare.com/tunnel/advanced/local-management/as-a-service/linux/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/

## Cloudflare Access

Create an Access application:

| Setting | Value |
|---|---|
| Application type | Self-hosted |
| DNS type | Public hostname |
| Public hostname | `<pawrrtal-hostname>` |
| Session duration | Operator choice |

Add an allow policy by email for the users who may open Pawrrtal. The
expected browser flow is:

```text
Cloudflare Access login -> Pawrrtal login -> app shell
```

Do not treat direct app HTML as a successful public verification. A CLI
probe without Access cookies should see an Access redirect or deny
response, not Pawrrtal HTML.

### OAuth Callback Paths

OAuth providers call back without a user's Cloudflare Access session.
If OAuth is enabled, decide how those callback paths are allowed through
Access:

```text
/api/v1/auth/oauth/*/callback
```

Use a narrow Access bypass or service-token policy for only those
callback paths if the provider cannot complete the callback through the
normal Access challenge. Keep the rest of the hostname protected by the
email allow policy.

## Environment

Backend secrets live in `backend/.env`. Minimum useful private setup:

```bash
ENV=prod
AUTH_SECRET=<high entropy secret>
WORKSPACE_ENCRYPTION_KEY=<fernet key>
WORKSPACE_BASE_DIR=/data/workspaces
ALLOWED_EMAILS=octavian@example.com,esther@example.com
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
CORS_ORIGINS=["https://<pawrrtal-hostname>"]
GOOGLE_OAUTH_REDIRECT_URI=https://<pawrrtal-hostname>/api/v1/auth/oauth/google/callback
APPLE_OAUTH_REDIRECT_URI=https://<pawrrtal-hostname>/api/v1/auth/oauth/apple/callback
OAUTH_POST_LOGIN_REDIRECT=https://<pawrrtal-hostname>/
GOOGLE_API_KEY=<or another provider key>
```

Leave `BACKEND_API_KEY` unset for the Cloudflared browser app. The
browser now calls same-origin `/api/v1`, `/auth`, and `/users` routes
directly, and Cloudflare Access is the public transport gate. Use
`BACKEND_API_KEY` only for server-to-server deployments where every
caller can inject `X-Pawrrtal-Key`.

Frontend server-side calls use:

```bash
BACKEND_INTERNAL_URL=http://127.0.0.1:8000
```

Set this when building or running the frontend outside Cloudflared's
path ingress, such as CI production-build E2E. Cloudflared public
traffic sends `/api/v1`, `/auth`, and `/users` directly to FastAPI
before those paths reach Next.js.

## Local Services

Start the app once and confirm both local origins respond:

```bash
just paw project up
just paw project status
```

For a persistent VPS process, install the user systemd service:

```bash
just paw project service install --linger
just paw project service status
```

The service runs `dev.ts`, which starts Next.js on `127.0.0.1:3000`
and FastAPI on `127.0.0.1:8000`. It does not expose a public port.
If this VPS should use Postgres instead of local SQLite, set
`PAWRRTAL_DEV_DATABASE_URL` before installing the service; the service
intentionally clears the generic `DATABASE_URL` so unrelated shell
state cannot leak into local project launches.

## Cloudflared Install

Authenticate Cloudflared with the Cloudflare account that owns the zone:

```bash
cloudflared tunnel login
```

Then let Paw CLI own the tunnel config:

```bash
just paw project cloudflared install \
  --hostname pawrrtal.octaviantocan.com \
  --tunnel-name pawrrtal
```

The command validates both local origins first, refuses non-loopback
origins, creates or reuses the named tunnel, writes the config, runs
`cloudflared tunnel ingress validate`, routes DNS, installs the
Cloudflared Linux service, and stores non-secret deployment state in the
Paw config directory.

The managed config lives at:

```text
/etc/cloudflared/config.yml
```

Expected config shape:

```yaml
tunnel: <uuid>
credentials-file: /etc/cloudflared/<uuid>.json
metrics: 127.0.0.1:20241

ingress:
  - hostname: <pawrrtal-hostname>
    path: ^/api/v1/.*
    service: http://127.0.0.1:8000
  - hostname: <pawrrtal-hostname>
    path: ^/auth/.*
    service: http://127.0.0.1:8000
  - hostname: <pawrrtal-hostname>
    path: ^/users/.*
    service: http://127.0.0.1:8000
  - hostname: <pawrrtal-hostname>
    service: http://127.0.0.1:3000
  - service: http_status:404
```

The CLI never prints tunnel credential JSON, origin cert contents,
Access service tokens, or other secrets.

## Verification

Run:

```bash
just paw project cloudflared verify \
  --hostname pawrrtal.octaviantocan.com \
  --tunnel-name pawrrtal
```

This checks:

- `cloudflared` exists.
- Frontend and backend origins are loopback and healthy.
- `/etc/cloudflared/config.yml` passes `cloudflared tunnel ingress validate`.
- `cloudflared tunnel info pawrrtal` succeeds.
- The system `cloudflared` service is present.
- The public hostname returns a Cloudflare Access challenge or deny
  response to an unauthenticated CLI probe.

For machine output:

```bash
just paw project cloudflared verify --hostname pawrrtal.octaviantocan.com --json
```

Status:

```bash
just paw project cloudflared status
```

Uninstall:

```bash
just paw project cloudflared uninstall
```

## Updating

```bash
git fetch
git checkout <release>
git submodule update --init --recursive
just install
cd backend
uv run alembic upgrade head
cd ..
just paw project service restart
just paw project cloudflared verify --hostname pawrrtal.octaviantocan.com
```

## Troubleshooting

### Public hostname shows Pawrrtal HTML without Access

The Access app is not protecting the hostname. Recheck the Access
application type, hostname, and policies. `paw project cloudflared
verify` should fail in this state.

### Browser passes Access but API calls fail

Check Cloudflared ingress order. `/api/v1`, `/auth`, and `/users` must
route to `http://127.0.0.1:8000` before the frontend catch-all route.

### CLI says local origins are unavailable

Run:

```bash
just paw project status
curl http://localhost:3000/
curl http://127.0.0.1:8000/api/v1/health
```

Fix local services before touching Cloudflare.

### OAuth callback fails

Check whether Cloudflare Access is challenging the provider callback.
Add a narrow bypass or service-token rule only for:

```text
/api/v1/auth/oauth/*/callback
```

### Chat replies do not stream

Cloudflared should pass Server-Sent Events through the tunnel. If
streaming regresses, verify that no additional reverse proxy or Worker
was added in front of the tunnel.

## Checklist

- [ ] Local frontend healthy on `http://localhost:3000`.
- [ ] Local backend healthy on `http://127.0.0.1:8000/api/v1/health`.
- [ ] Cloudflare Access self-hosted app protects the public hostname.
- [ ] Email allow policy includes every intended user.
- [ ] OAuth callback bypass/service-token policy considered if OAuth is enabled.
- [ ] `paw project cloudflared install` completed.
- [ ] `paw project cloudflared verify` passes.
- [ ] Browser flow is `Cloudflare Access -> Pawrrtal login -> app shell`.
