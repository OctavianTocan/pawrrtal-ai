---
# pawrrtal-szd2
title: dev.ts — start Effect TS API on :8001
status: todo
type: feature
priority: high
tags:
    - backend-ts
    - dev
    - devx
created_at: 2026-06-08T12:36:03Z
updated_at: 2026-06-08T12:36:03Z
---

## Goal

Make `just dev` (and the underlying `dev.ts`) start the Effect TS strangler API on `:8001`
alongside the Next.js frontend and the Python FastAPI backend, so local dev exercises the
whole stack the way it ships in production.

## Why now

- `dev.ts:55-72` already runs the frontend and the Python backend; the Effect TS API is the
  only server in the repo that doesn't come up under `just dev`.
- `scripts/dev-ports.ts:27` declares `DEV_BACKEND_TS_PORT = 8001` with a comment
  "not wired in `dev.ts` yet." That comment goes stale the moment the wiring lands.
- The pilot's "behavioral parity" claim (plan §1) is only credible if a developer can
  curl `:8001` and `:8000` from the same `just dev` session.
- Auth is not required for `:8001` to boot — `STUB_USER_ID` is enough for local dev parity
  (matches how `paw` smoke tests are scoped).

## Files

- `dev.ts` — add a third concurrent promise for the Effect TS API + free `:8001` on the
  existing `lsof` line
- `scripts/dev-ports.ts` — delete the "not wired in `dev.ts` yet" comment on
  `DEV_BACKEND_TS_PORT` (one line edit)
- `backend-ts/README.md` — optional, add a one-line note that `just dev` starts `:8001`
  (only if it's already mentioning the port; verified it does at line 47)

## Steps

### 1. Add the third promise to `dev.ts`

Edit `dev.ts`. The file already has:

```typescript
// Free up dev ports before starting (handles ghost processes from previous runs).
// `.nothrow()` keeps the script running even if no process is bound to the port.
await $`lsof -ti:${DEV_FRONTEND_PORT} | xargs kill -9`.quiet().nothrow();
await $`lsof -ti:${DEV_BACKEND_PORT} | xargs kill -9`.quiet().nothrow();
```

Add the TS port to that block:

```typescript
await $`lsof -ti:${DEV_FRONTEND_PORT} | xargs kill -9`.quiet().nothrow();
await $`lsof -ti:${DEV_BACKEND_PORT} | xargs kill -9`.quiet().nothrow();
await $`lsof -ti:${DEV_BACKEND_TS_PORT} | xargs kill -9`.quiet().nothrow();
```

Then, after the `backendPromise` block (current line ~73), add the TS API block:

```typescript
// Effect TS strangler on :8001. Opt out with PAWRRTAL_SKIP_TS_API=1 — the
// default is on now that Service/Repo/Http tests in backend-ts pass
// (slice 1 of this work). Auth (cookie middleware) is still pending;
// the server uses STUB_USER_ID for now.
const skipTsApi = process.env.PAWRRTAL_SKIP_TS_API === '1';
if (!skipTsApi) {
	console.log(`Starting Effect TS API on http://127.0.0.1:${DEV_BACKEND_TS_PORT}`);
}

const tsApiPromise = skipTsApi
	? $({ reject: false })`echo skipping Effect TS API on :${DEV_BACKEND_TS_PORT}`.quiet()
	: $`bun --filter @pawrrtal/api dev`.quiet(false);
```

Update the existing `await Promise.all` at the bottom of the file:

```typescript
await Promise.all([frontendPromise, backendPromise, tsApiPromise]);
```

Update the existing status log line (currently `dev.ts:62-64`):

```typescript
console.log(
	`Starting dev servers — frontend on ${DEV_FRONTEND_URL}, backend on ${DEV_BACKEND_URL}, Effect TS on http://127.0.0.1:${DEV_BACKEND_TS_PORT}`
);
```

(If `skipTsApi` is set, adjust to omit the "Effect TS on …" suffix; the inner `console.log`
above already conditions on it.)

### 2. Update the port-contract comment

Edit `scripts/dev-ports.ts:27`. Change:

```typescript
/**
 * Port reserved for the Effect TypeScript strangler API (not wired in `dev.ts` yet).
 *
 * Python FastAPI remains on {@link DEV_BACKEND_PORT} until route parity lands.
 */
export const DEV_BACKEND_TS_PORT = 8001;
```

to:

```typescript
/**
 * Port the Effect TypeScript strangler API listens on locally.
 *
 * Started by `dev.ts` (opt out with `PAWRRTAL_SKIP_TS_API=1`). Python FastAPI
 * remains canonical on {@link DEV_BACKEND_PORT} until route parity lands on
 * the TS stack.
 */
export const DEV_BACKEND_TS_PORT = 8001;
```

### 3. README touch-up (only if the README mentions the port)

`backend-ts/README.md:45-49` has a "Dev ports" table. If the wording is still
"planned" / "not started", change to "Started by `just dev` (set
`PAWRRTAL_SKIP_TS_API=1` to opt out)." If it's already neutral, leave it alone.

### 4. Verify locally

```bash
just dev
# In another terminal:
curl -sI http://127.0.0.1:8001/health
# Expect: HTTP/1.1 204 No Content

curl -s http://127.0.0.1:8001/openapi.json | head -c 200
# Expect: JSON with "/api/v1/projects" in paths

# Test the opt-out
PAWRRTAL_SKIP_TS_API=1 just dev
# Expect: log line says "skipping Effect TS API on :8001" and :8001 is not bound
lsof -ti:8001
# Expect: empty (no PID)
```

### 5. Manual parity check (informational, not a gate)

With `just dev` running and a user signed in via the frontend, capture the `session_token`
cookie and:

```bash
# Compare list projects on both backends
curl -s -H "Cookie: session_token=$COOKIE" http://127.0.0.1:8000/api/v1/projects
curl -s -H "Cookie: session_token=$COOKIE" http://127.0.0.1:8001/api/v1/projects
# (Note: :8001 will return 401 today because of STUB_USER_ID — this is a
# known Phase C-1 gap. We are NOT fixing it in this slice.)
```

## Rules

- **Do not** change the order of the existing `frontendPromise` / `backendPromise`
  block. Just add a third promise and add it to the `Promise.all`.
- **Do not** default to off. The plan's "Optional flag" was the pre-slice-1 caution;
  with tests green, default-on is the point. The flag exists for escape (`paw` smoke
  tests, frontend-only iteration).
- **Do not** edit `apps/api/src/Main.ts` or any other runtime file. This slice is
  dev-orchestration only.
- **Do not** remove the `STUB_USER_ID` constant from `Http.ts:12` — auth is Phase C-1.
- Port kill uses the exact same `lsof | xargs kill -9` pattern as the existing two
  lines. No new dependency, no new process.

## Out of scope

- Frontend env / proxy to hit `:8001` for projects only (plan §6: "Frontend switch
  before auth + tests hides stub bugs and auth gaps"). Phase D-2.
- Postgres / `@effect/sql-pg` for Railway production (Phase D-3).
- In-app "is the Effect TS API up?" health badge in the UI.
- `paw project up` integration (defer until parity is real, not stub-auth).
