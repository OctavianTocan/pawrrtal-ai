/**
 * Production loopback orchestrator for the Cloudflared deployment.
 *
 * Builds the standalone Next.js server, then runs it beside FastAPI on
 * loopback ports. Cloudflared owns the public surface.
 */
import { type ChildProcess, spawn } from 'node:child_process';
import { access, cp, mkdir, rm } from 'node:fs/promises';
import { $ } from 'bun';
import { DEV_BACKEND_PORT, DEV_FRONTEND_BIND_HOST, DEV_FRONTEND_PORT } from './scripts/dev-ports';

const CACHE_DIR = '.cache';
const SHUTDOWN_TIMEOUT_MS = 10_000;
const FRONTEND_DIR = 'frontend';
const STANDALONE_APP_DIR = `${FRONTEND_DIR}/.next/standalone/frontend`;
const STANDALONE_SERVER = `${STANDALONE_APP_DIR}/server.js`;
const BACKEND_BIND_HOST = envValue('PAWRRTAL_BACKEND_HOST') ?? '127.0.0.1';
const BACKEND_PORT = Number(envValue('PAWRRTAL_BACKEND_PORT') ?? DEV_BACKEND_PORT);
const FRONTEND_BIND_HOST = envValue('HOSTNAME') ?? DEV_FRONTEND_BIND_HOST;
const FRONTEND_PORT = Number(envValue('PORT') ?? DEV_FRONTEND_PORT);
const BACKEND_URL = `http://${BACKEND_BIND_HOST}:${BACKEND_PORT}`;
const FRONTEND_URL = `http://${FRONTEND_BIND_HOST}:${FRONTEND_PORT}`;

await mkdir(`${CACHE_DIR}/uv`, { recursive: true });
await mkdir(`${CACHE_DIR}/xdg`, { recursive: true });

setEnv('NODE_ENV', 'production');
setEnvDefault('NEXT_TELEMETRY_DISABLED', '1');
setEnvDefault('UV_CACHE_DIR', `${CACHE_DIR}/uv`);
setEnvDefault('XDG_CACHE_HOME', `${CACHE_DIR}/xdg`);
setEnvDefault('BACKEND_INTERNAL_URL', BACKEND_URL);
setEnvDefault('HOSTNAME', FRONTEND_BIND_HOST);
setEnvDefault('PORT', String(FRONTEND_PORT));
setEnv('ENV', 'prod');

logInfo('Building frontend production bundle');
await $`bun --filter pawrrtal build`;
await access(STANDALONE_SERVER);
await copyStandaloneAssets();

logInfo(`Starting Pawrrtal production services: ${FRONTEND_URL} + ${BACKEND_URL}`);

type ManagedProcess = {
	name: string;
	child: ChildProcess;
};

function envValue(name: string): string | undefined {
	return process.env[name];
}

function setEnv(name: string, value: string): void {
	process.env[name] = value;
}

function setEnvDefault(name: string, value: string): void {
	process.env[name] ??= value;
}

function logInfo(message: string): void {
	process.stderr.write(`${message}\n`);
}

async function copyStandaloneAssets(): Promise<void> {
	const staticTarget = `${STANDALONE_APP_DIR}/.next/static`;
	const publicTarget = `${STANDALONE_APP_DIR}/public`;
	await rm(staticTarget, { recursive: true, force: true });
	await rm(publicTarget, { recursive: true, force: true });
	await cp(`${FRONTEND_DIR}/.next/static`, staticTarget, { recursive: true });
	await cp(`${FRONTEND_DIR}/public`, publicTarget, { recursive: true });
}

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
				logInfo(`${processInfo.name} exited from signal ${signal}`);
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
	startManagedProcess('frontend', 'node', [STANDALONE_SERVER]),
	startManagedProcess('backend', 'uv', [
		'run',
		'--project',
		'backend',
		'uvicorn',
		'main:app',
		'--app-dir',
		'backend',
		'--host',
		BACKEND_BIND_HOST,
		'--port',
		String(BACKEND_PORT),
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
