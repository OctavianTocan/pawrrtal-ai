# Functional Verification

## Context

Use this after deployment, restart, migration, or a suspected user-visible regression. The goal is to prove real behavior, not merely process uptime.

## Steps

### 1. Start from local health

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsSI http://127.0.0.1:3000 || curl -fsSI http://127.0.0.1:53001
```

### 2. Verify auth and API flows with Paw CLI

```bash
cd backend
uv run paw doctor --json
uv run paw auth status --json
uv run paw verify chat-roundtrip --json
uv run paw verify model-switch --json
uv run paw verify lcm --json
```

If the CLI fails before making HTTP requests because local env points at a bad database, document that and verify through live HTTP plus service logs. Do not treat the shell environment as live truth.

### 3. Verify provider and full suites when shipping runtime changes

```bash
cd backend
uv run paw verify all-providers --json
uv run paw verify all --json
```

Use focused suites first when debugging. Use `verify all` as a release gate, not as the first diagnostic tool.

When the claim involves subscription-auth providers or live model behavior, run at least one real model roundtrip through Paw with the same workspace/user the app uses:

```bash
cd backend
paw verify chat-roundtrip --model <provider:model> --json
```

Do not claim "real models work" from mocked tests, provider list output, a token-presence check, or a simulated channel path. The evidence must include a successful final response from a live model call and the corresponding Paw verifier result.

### 4. Verify frontend and browser behavior

Run project gates from the checkout that will be deployed:

```bash
cd frontend && bun run check
cd frontend && bun run test -- features/auth/LoginFormView.test.tsx features/auth/dev-login-availability.test.ts lib/api.url-resolution.test.ts next.config.rewrites.test.ts
```

For actual browser proof, use Playwright against the live local origins:

```bash
cd frontend
E2E_BASE_URL=http://127.0.0.1:3000 E2E_API_URL=http://127.0.0.1:8000 bunx --bun playwright test e2e/login.spec.ts --project=chromium
```

If the live frontend still runs on `53001`, use that in `E2E_BASE_URL`.

### 5. Verify public URL shape

```bash
curl -sSI https://pawrrtal.octaviantocan.com | sed -n '1,30p'
```

Expected unauthenticated result: Cloudflare Access challenge/redirect or a protected response, not raw Pawrrtal HTML. Use a real browser session after Access to prove app shell, login, navigation, and one backend-backed screen.

### 6. Report evidence

Summarize:

- Running branch and commit.
- Process owner and ports.
- Local health result.
- Public Access result.
- Paw verifier results.
- Real model and channel proof when relevant.
- Browser smoke result.
- Any skipped check and why it was not authoritative.
