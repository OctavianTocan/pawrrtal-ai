/**
 * Frontend + backend server lifecycle for the Electrobun shell.
 *
 * Mirrors electron/src/server.ts. Two modes:
 *
 *   dev  — spawns `bun run dev` from the monorepo root, which runs dev.ts:
 *           starts Next.js on :3001 AND the FastAPI backend on :8000.
 *           PAWRRTAL_REPO_ROOT env var (set by `bun run start` in electrobun/)
 *           tells us where the monorepo root is.
 *
 *   prod — spawns the Next.js standalone server bundled inside the app
 *           on a dynamically allocated free port, then returns its URL.
 *
 * @module
 */

import { createServer } from 'node:net';
import path from 'node:path';
import { DEV_FRONTEND_PORT } from '../../../scripts/dev-ports';

export interface StartedServer {
	url: string;
	stop: () => Promise<void>;
}

// ``DEV_FRONTEND_PORT`` is the canonical shared constant — imported from
// the monorepo's ``scripts/dev-ports.ts`` so this shell, dev.ts, and any
// future consumer agree on the value without having to keep three
// literal copies in sync.

// ---------------------------------------------------------------------------
// Port helpers
// ---------------------------------------------------------------------------

/**
 * Poll `host:port` every 500 ms until a TCP connection succeeds or
 * `timeoutMs` elapses.
 */
function waitForPort(port: number, host: string, timeoutMs: number): Promise<void> {
	return new Promise((resolve, reject) => {
		const deadline = Date.now() + timeoutMs;

		const attempt = () => {
			if (Date.now() >= deadline) {
				reject(new Error(`Port ${host}:${port} did not open within ${timeoutMs}ms`));
				return;
			}

			const sock = new (require('node:net').Socket as typeof import('node:net').Socket)();
			sock.setTimeout(250);
			sock.once('connect', () => {
				sock.destroy();
				resolve();
			});
			sock.once('timeout', () => {
				sock.destroy();
				setTimeout(attempt, 500);
			});
			sock.once('error', () => {
				sock.destroy();
				setTimeout(attempt, 500);
			});
			sock.connect(port, host);
		};

		attempt();
	});
}

/** Ask the OS for a free TCP port. */
function allocateFreePort(): Promise<number> {
	return new Promise((resolve, reject) => {
		const probe = createServer();
		probe.unref();
		probe.on('error', reject);
		probe.listen(0, () => {
			const address = probe.address();
			if (address && typeof address === 'object') {
				const { port } = address;
				probe.close(() => resolve(port));
			} else {
				probe.close(() => reject(new Error('Failed to allocate a free port.')));
			}
		});
	});
}

// ---------------------------------------------------------------------------
// Dev server
// ---------------------------------------------------------------------------

/**
 * Spawn `bun run dev` at `<repo>/` (runs `dev.ts`: Next.js on DEV_FRONTEND_PORT
 * and FastAPI on :8000) and wait for the frontend port to accept connections.
 *
 * The monorepo root is read from PAWRRTAL_REPO_ROOT (injected by the
 * `bun run start` script in package.json).
 */
async function startDevServer(): Promise<StartedServer> {
	const repoRoot = process.env.PAWRRTAL_REPO_ROOT;
	if (!repoRoot) {
		throw new Error(
			'PAWRRTAL_REPO_ROOT is not set. ' +
				'Run `bun run start` from the electrobun/ directory — the script sets it automatically.'
		);
	}
	// dev.ts starts both:
	//   - Next.js frontend  (bun --filter pawrrtal dev) on :3001
	//   - FastAPI backend   (uvicorn main:app)           on :8000
	// Use process.execPath (bundled bun) to avoid PATH issues on macOS app bundles.
	const child = Bun.spawn([process.execPath, 'run', 'dev'], {
		cwd: repoRoot,
		env: { ...(process.env as Record<string, string>) },
		stdout: 'inherit',
		stderr: 'inherit',
	});

	// If the process exits immediately it means the command failed
	// (e.g., bun not in PATH, missing node_modules). Surface it fast.
	const exitRaceMs = 3_000;
	const exitEarly = await Promise.race([
		child.exited.then((code) => code),
		new Promise<null>((r) => setTimeout(() => r(null), exitRaceMs)),
	]);
	if (exitEarly !== null) {
		throw new Error(
			`Next.js dev server process exited immediately with code ${exitEarly}. ` +
				`Check that 'bun install' has been run from the repo root and that ` +
				`'bun run dev' works inside frontend/.`
		);
	}

	// Give Next.js up to 120s to compile and bind the port.
	await waitForPort(DEV_FRONTEND_PORT, 'localhost', 120_000);

	return {
		url: `http://localhost:${DEV_FRONTEND_PORT}`,
		stop: async () => {
			child.kill();
		},
	};
}

// ---------------------------------------------------------------------------
// Production server
// ---------------------------------------------------------------------------

/**
 * Resolve the root of the bundled Next.js standalone tree.
 *
 * Electrobun places app resources under the .app bundle's Resources/.
 * The standalone tree is copied there during `electrobun build --env=stable`.
 *
 * Layout inside the bundle:
 *   Resources/
 *     app/bun/index.js   ← this process
 *     frontend/          ← Next.js standalone root
 */
function resolveStandaloneRoot(): string {
	// import.meta.dir is the directory of the current source file as
	// seen by Bun's bundler. In a packaged Electrobun app this resolves
	// to the Resources/app/bun/ directory.
	const appBunDir = import.meta.dir;
	return path.resolve(appBunDir, '..', '..', 'frontend');
}

async function startProductionServer(): Promise<StartedServer> {
	const port = await allocateFreePort();
	const standaloneRoot = resolveStandaloneRoot();
	const entry = path.join(standaloneRoot, 'server.js');

	const env: Record<string, string> = {
		...(process.env as Record<string, string>),
		PORT: String(port),
		HOSTNAME: '127.0.0.1',
	};

	const child = Bun.spawn([process.execPath, entry], {
		cwd: standaloneRoot,
		env,
		stdout: 'inherit',
		stderr: 'inherit',
	});

	await waitForPort(port, '127.0.0.1', 30_000);

	return {
		url: `http://127.0.0.1:${port}`,
		stop: async () => {
			child.kill();
		},
	};
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function startNextServer(options: { isDev: boolean }): Promise<StartedServer> {
	return options.isDev ? startDevServer() : startProductionServer();
}
