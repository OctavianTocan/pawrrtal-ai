/**
 * Dev orchestrator: runs the Next.js frontend, FastAPI backend, and the
 * Effect TS strangler API side-by-side on plain localhost. Frontend /
 * backend ports come from `scripts/dev-ports.ts`, the single source of
 * truth shared with the Electrobun shell and the frontend's
 * `package.json` `dev` script. No proxies, no HTTPS, no special
 * routing — just three processes.
 */
import { mkdir } from 'node:fs/promises';
import { $ } from 'bun';
import {
	DEV_BACKEND_PORT,
	DEV_BACKEND_TS_PORT,
	DEV_BACKEND_URL,
	DEV_FRONTEND_PORT,
	DEV_FRONTEND_URL,
} from './scripts/dev-ports';

const SQLITE_DB_FILENAME_PREFIX = 'pawrrtal';
const MAX_BRANCH_FILENAME_LENGTH = 80;
const DEV_CACHE_DIR = '.cache';
const DEV_DATABASE_URL_ENV = 'PAWRRTAL_DEV_DATABASE_URL';
const SKIP_TS_API_ENV = 'PAWRRTAL_SKIP_TS_API';

await mkdir(`${DEV_CACHE_DIR}/uv`, { recursive: true });
await mkdir(`${DEV_CACHE_DIR}/xdg`, { recursive: true });
process.env.UV_CACHE_DIR ??= `${DEV_CACHE_DIR}/uv`;
process.env.XDG_CACHE_HOME ??= `${DEV_CACHE_DIR}/xdg`;
process.env.DATABASE_URL = process.env[DEV_DATABASE_URL_ENV] ?? '';

/**
 * Resolve a filesystem-safe SQLite filename scoped to the current git branch
 * so switching branches no longer trashes a shared `pawrrtal.db`. Returns
 * `null` when there is no current branch (detached HEAD, not a git repo,
 * empty output), letting the backend's built-in default apply.
 */
async function sqliteDbFilenameForBranch(): Promise<string | null> {
	const result = await $`git rev-parse --abbrev-ref HEAD`.quiet().nothrow();
	if (result.exitCode !== 0) return null;
	const branch = result.stdout.toString().trim();
	if (!branch || branch === 'HEAD') return null;
	const sanitized = branch
		.replace(/[^A-Za-z0-9._-]+/g, '-')
		.replace(/-+/g, '-')
		.replace(/^[-.]+|[-.]+$/g, '')
		.slice(0, MAX_BRANCH_FILENAME_LENGTH);
	if (!sanitized) return null;
	return `${SQLITE_DB_FILENAME_PREFIX}-${sanitized}.db`;
}

// Effect TS strangler opt-out: `PAWRRTAL_SKIP_TS_API=1` skips bringing up
// the API on :8001. Default is on now that the Projects slice has tests
// (slice 1 of `pawrrtal-szd2`); the flag exists for `paw` smoke tests
// and frontend-only iteration. Auth is still pending (Phase C-1) — the
// API uses `STUB_USER_ID` for now.
const skipTsApi = process.env[SKIP_TS_API_ENV] === '1';

// Free up dev ports before starting (handles ghost processes from previous runs).
// `.nothrow()` keeps the script running even if no process is bound to the port.
await $`lsof -ti:${DEV_FRONTEND_PORT} | xargs kill -9`.quiet().nothrow();
await $`lsof -ti:${DEV_BACKEND_PORT} | xargs kill -9`.quiet().nothrow();
if (!skipTsApi) {
	await $`lsof -ti:${DEV_BACKEND_TS_PORT} | xargs kill -9`.quiet().nothrow();
}

// Clear Next.js dev lock to avoid the "Unable to acquire lock" error on restart.
await $`rm -rf frontend/.next/dev/lock`.quiet().nothrow();

// Scope the implicit SQLite database to the current git branch. Honour an
// existing `SQLITE_DB_FILENAME` override (one-off experiments). Local dev
// defaults to SQLite even when the shell exports a global DATABASE_URL; set
// PAWRRTAL_DEV_DATABASE_URL to opt into a non-SQLite dev database.
if (!process.env.SQLITE_DB_FILENAME) {
	const branchDbFilename = await sqliteDbFilenameForBranch();
	if (branchDbFilename) {
		process.env.SQLITE_DB_FILENAME = branchDbFilename;
		console.log(`Using branch-scoped SQLite database: ${branchDbFilename}`);
	}
}

if (skipTsApi) {
	console.log(
		`Starting dev servers — frontend on ${DEV_FRONTEND_URL}, backend on ${DEV_BACKEND_URL} (Effect TS on :${DEV_BACKEND_TS_PORT} skipped — ${SKIP_TS_API_ENV}=1)`
	);
} else {
	console.log(
		`Starting dev servers — frontend on ${DEV_FRONTEND_URL}, backend on ${DEV_BACKEND_URL}, Effect TS on http://127.0.0.1:${DEV_BACKEND_TS_PORT}`
	);
}

// Frontend: plain Next.js dev server. Workspace package, run via bun --filter.
const frontendPromise = $`bun --filter pawrrtal dev`.quiet(false);

// Backend: explicit ASGI target via uvicorn. `main.app` is wrapped in CORS
// middleware, so FastAPI CLI discovery cannot treat it as a raw FastAPI instance.
const backendPromise =
	$`uv run --project backend uvicorn main:app --app-dir backend --host 127.0.0.1 --port ${DEV_BACKEND_PORT} --reload --reload-dir backend`.quiet(
		false
	);

// Effect TS strangler: `bun --filter @pawrrtal/api dev` runs `src/index.ts`
// which imports `./Main.ts` — the bootstrap that launches the server on
// :8001 (slice 3 of `pawrrtal-szd2`). When skipped, we just await a
// never-resolving promise so the process stays up alongside the other
// two (the `await Promise.all([...])` at the bottom never settles).
const tsApiPromise: Promise<void> = skipTsApi
	? new Promise(() => {
			// Intentionally never resolves — the surrounding `await Promise.all`
			// keeps the dev orchestrator running until SIGINT.
		})
	: $`bun --filter @pawrrtal/api dev`.quiet(false);

await Promise.all([frontendPromise, backendPromise, tsApiPromise]);
