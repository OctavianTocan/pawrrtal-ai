/**
 * Shared dev-port contract for the monorepo.
 *
 * The frontend dev server port and backend dev server port are a
 * cross-process contract (referenced from `dev.ts`, the Electrobun
 * shell's lifecycle module, comments in handbook docs, etc.). Owning
 * the literal values here gives every consumer one canonical import
 * and stops drift between repo root, frontend, and desktop shell.
 *
 * The frontend dev host/port also appears in `frontend/package.json`
 * (`scripts.dev`: `next dev --hostname 127.0.0.1 --port 53001`). Those
 * values must stay in sync with {@link DEV_FRONTEND_BIND_HOST} and
 * {@link DEV_FRONTEND_PORT}; the verification helper below is the gate
 * for that constraint — call it from CI or pre-commit if needed.
 *
 * @see frontend/package.json
 * @see dev.ts
 * @see electrobun/src/bun/server.ts
 * @see electron/src/server.ts (if present)
 */

/**
 * Port the Next.js dev server listens on locally.
 *
 * Must match the `--port` flag in `frontend/package.json` -> `scripts.dev`.
 * Verified by {@link assertFrontendPortMatchesPackageJson}.
 */
export const DEV_FRONTEND_PORT = 53001;

/**
 * Host the Next.js dev server binds to locally.
 *
 * Keep this on loopback so Cloudflared, not the raw dev port, is the
 * deployment's public surface.
 */
export const DEV_FRONTEND_BIND_HOST = '127.0.0.1';

/**
 * Port the FastAPI dev server listens on locally.
 *
 * Driven from `dev.ts`'s uvicorn invocation; the value isn't currently
 * embedded in any other file but lives here so the same export pattern
 * applies to both ports.
 */
export const DEV_BACKEND_PORT = 8000;

/**
 * URL the desktop shell points at when running against `bun run dev`.
 *
 * Centralised so the dev shell + status log + any future
 * health-probe consumer all read the same string.
 */
export const DEV_FRONTEND_URL = `http://localhost:${DEV_FRONTEND_PORT}`;

/**
 * URL the backend exposes during `bun run dev`.
 *
 * Mirrors {@link DEV_FRONTEND_URL} for symmetry; the backend stays on
 * `127.0.0.1` to match what uvicorn binds inside `dev.ts`.
 */
export const DEV_BACKEND_URL = `http://127.0.0.1:${DEV_BACKEND_PORT}`;

/**
 * Verify that `frontend/package.json` still encodes the canonical
 * frontend dev port.
 *
 * This is the assertion side of the package.json escape hatch:
 * package-script command strings can't easily import this module, so
 * the check lives here and any consumer (a pre-push hook, a CI step)
 * calls it to fail fast on drift.
 *
 * @param packageJsonText - The textual contents of `frontend/package.json`.
 *   The function intentionally takes the raw string rather than a parsed
 *   shape so callers can read it once with `Bun.file().text()` /
 *   `fs.readFileSync` without picking a JSON schema.
 * @returns `true` when the file references the canonical port via
 *   `next dev --hostname <DEV_FRONTEND_BIND_HOST> --port <DEV_FRONTEND_PORT>`.
 *   Throws an `Error` describing the mismatch when the host or port literal
 *   is missing or differs.
 */
export function assertFrontendPortMatchesPackageJson(packageJsonText: string): true {
	const expected = `next dev --hostname ${DEV_FRONTEND_BIND_HOST} --port ${DEV_FRONTEND_PORT}`;
	if (!packageJsonText.includes(expected)) {
		throw new Error(
			`frontend/package.json does not reference the canonical dev host/port. ` +
				`Expected the substring '${expected}' in scripts.dev; update package.json ` +
				`or scripts/dev-ports.ts so the two match.`
		);
	}
	return true;
}
