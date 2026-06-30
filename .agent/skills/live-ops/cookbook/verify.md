# Functional Verification

## Context

Use this after deployment, restart, migration, or a suspected user-visible regression. The goal is to prove real behavior, not merely process uptime.

## Steps

### 1. Start from local health

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsSI http://127.0.0.1:3000 || curl -fsSI http://127.0.0.1:53001
```

### 2. Verify local CLI health

```bash
just paw doctor --json
just paw context --json
```

The current Bun CLI slice covers local health, active context, and completions.
Auth, provider, and chat verifier command groups have not been reintroduced yet.
For those claims, verify through live HTTP, focused tests, and service logs.
Do not treat shell environment as live truth.

### 3. Verify provider and full suites when shipping runtime changes

Use focused suites first when debugging. Use broad release gates only after the
focused evidence points at the right layer.

When the claim involves subscription-auth providers or live model behavior, run
at least one real model roundtrip through the live app or a focused backend test
with the same workspace/user the app uses. The model must mirror the
production/channel default being claimed.

Do not claim "real models work" from mocked tests, provider list output, a token-presence check, or a simulated channel path. The evidence must include a successful final response from a live model call and the route, log, or test evidence that produced it.

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
