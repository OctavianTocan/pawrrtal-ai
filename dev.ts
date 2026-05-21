/**
 * Dev orchestrator: runs the Next.js frontend and FastAPI backend side-by-side
 * on plain localhost. Frontend on :3001, backend on :8000. No proxies, no HTTPS,
 * no special routing — just the two processes.
 */
import { $ } from 'bun';

const SQLITE_DB_FILENAME_PREFIX = 'pawrrtal';
const MAX_BRANCH_FILENAME_LENGTH = 80;

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

// Free up dev ports before starting (handles ghost processes from previous runs).
// `.nothrow()` keeps the script running even if no process is bound to the port.
await $`lsof -ti:3001 | xargs kill -9`.quiet().nothrow();
await $`lsof -ti:8000 | xargs kill -9`.quiet().nothrow();

// Clear Next.js dev lock to avoid the "Unable to acquire lock" error on restart.
await $`rm -rf frontend/.next/dev/lock`.quiet().nothrow();

// Scope the implicit SQLite database to the current git branch. Honour an
// existing `SQLITE_DB_FILENAME` override (one-off experiments) and never
// overwrite an explicit `DATABASE_URL` — the backend's config falls through
// to `SQLITE_DB_FILENAME` only when `DATABASE_URL` is empty.
if (!process.env.SQLITE_DB_FILENAME) {
	const branchDbFilename = await sqliteDbFilenameForBranch();
	if (branchDbFilename) {
		process.env.SQLITE_DB_FILENAME = branchDbFilename;
		console.log(`Using branch-scoped SQLite database: ${branchDbFilename}`);
	}
}

console.log(
	'Starting dev servers — frontend on http://localhost:3001, backend on http://localhost:8000'
);

// Frontend: plain Next.js dev server. Workspace package, run via bun --filter.
const frontendPromise = $`bun --filter pawrrtal dev`.quiet(false);

// Backend: explicit ASGI target via uvicorn. `main.app` is wrapped in CORS
// middleware, so FastAPI CLI discovery cannot treat it as a raw FastAPI instance.
const backendPromise =
	$`uv run --project backend uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload --reload-dir backend`.quiet(
		false
	);

await Promise.all([frontendPromise, backendPromise]);
