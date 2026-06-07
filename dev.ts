/**
 * Dev orchestrator: runs the Next.js frontend and FastAPI backend side-by-side
 * on plain localhost. Frontend / backend ports come from `scripts/dev-ports.ts`,
 * the source of truth shared with the frontend's package.json `dev` script.
 * Next rewrites same-origin backend paths to FastAPI in local dev.
 */
import { type ChildProcess, spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { createServer } from 'node:net';
import { $ } from 'bun';
import {
	DEV_BACKEND_PORT,
	DEV_BACKEND_URL,
	DEV_FRONTEND_BIND_HOST,
	DEV_FRONTEND_PORT,
	DEV_FRONTEND_URL,
} from './scripts/dev-ports';

const SQLITE_DB_FILENAME_PREFIX = 'pawrrtal';
const MAX_BRANCH_FILENAME_LENGTH = 80;
const DEV_CACHE_DIR = '.cache';
const DEV_DATABASE_URL_ENV = 'PAWRRTAL_DEV_DATABASE_URL';
const SHUTDOWN_TIMEOUT_MS = 10_000;

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

async function assertPortAvailable(port: number, host: string): Promise<void> {
	await new Promise<void>((resolve, reject) => {
		const server = createServer();
		server.once('error', reject);
		server.listen({ port, host }, () => {
			server.close((error) => {
				if (error) reject(error);
				else resolve();
			});
		});
	}).catch((error: NodeJS.ErrnoException) => {
		const address = `${host}:${port}`;
		throw new Error(
			`Dev port ${address} is already in use or cannot be bound (${error.message}). ` +
				'Stop the existing dev server before starting Pawrrtal.'
		);
	});
}

await assertPortAvailable(DEV_FRONTEND_PORT, DEV_FRONTEND_BIND_HOST);
await assertPortAvailable(DEV_BACKEND_PORT, '127.0.0.1');

await $`rm -rf frontend/.next/dev/lock`.quiet().nothrow();

if (!process.env.SQLITE_DB_FILENAME) {
	const branchDbFilename = await sqliteDbFilenameForBranch();
	if (branchDbFilename) {
		process.env.SQLITE_DB_FILENAME = branchDbFilename;
		console.log(`Using branch-scoped SQLite database: ${branchDbFilename}`);
	}
}

console.log(
	`Starting dev servers — frontend on ${DEV_FRONTEND_URL}, backend on ${DEV_BACKEND_URL}`
);

type ManagedProcess = {
	name: string;
	child: ChildProcess;
};

function startManagedProcess(
	name: string,
	command: string,
	args: readonly string[]
): ManagedProcess {
	const child = spawn(command, [...args], {
		cwd: process.cwd(),
		detached: true,
		env: process.env,
		stdio: 'inherit',
	});
	return { name, child };
}

function waitForExit(processInfo: ManagedProcess): Promise<number> {
	return new Promise((resolve) => {
		processInfo.child.once('exit', (code, signal) => {
			if (signal) {
				console.error(`${processInfo.name} exited from signal ${signal}`);
				resolve(1);
				return;
			}
			resolve(code ?? 1);
		});
	});
}

async function stopProcess(processInfo: ManagedProcess): Promise<void> {
	const pid = processInfo.child.pid;
	if (!pid || processInfo.child.exitCode !== null) return;
	try {
		process.kill(-pid, 'SIGTERM');
	} catch (error) {
		if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error;
	}
	await Promise.race([
		waitForExit(processInfo),
		new Promise((resolve) => setTimeout(resolve, SHUTDOWN_TIMEOUT_MS)),
	]);
	if (processInfo.child.exitCode !== null) return;
	try {
		process.kill(-pid, 'SIGKILL');
	} catch (error) {
		if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error;
	}
}

const managedProcesses: ManagedProcess[] = [
	startManagedProcess('frontend', 'bun', ['--filter', 'pawrrtal', 'dev']),
	startManagedProcess('backend', 'uv', [
		'run',
		'--project',
		'backend',
		'uvicorn',
		'main:app',
		'--app-dir',
		'backend',
		'--host',
		'127.0.0.1',
		'--port',
		String(DEV_BACKEND_PORT),
		'--reload',
		'--reload-dir',
		'backend',
	]),
];

let shuttingDown = false;

async function shutdown(exitCode: number): Promise<never> {
	if (shuttingDown) process.exit(exitCode);
	shuttingDown = true;
	await Promise.all(managedProcesses.map((processInfo) => stopProcess(processInfo)));
	process.exit(exitCode);
}

process.once('SIGINT', () => void shutdown(130));
process.once('SIGTERM', () => void shutdown(143));

const exitCode = await Promise.race(
	managedProcesses.map((processInfo) => waitForExit(processInfo))
);
await shutdown(exitCode);
