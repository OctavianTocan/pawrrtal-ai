/**
 * OS-level lifecycle for the standalone actor server (`src/server.ts`).
 *
 * Shared by M6 (cold-restart durability) and M7 (exercising the wrapped Rivet
 * client). A "cold restart" requires killing BOTH the server process and the
 * engine it spawned — when the engine dies the rivetkit envoy retries forever
 * and never respawns it (observed in M6), so we kill the engine by name too.
 */
import { type ChildProcess, spawn } from 'node:child_process';
import { connect as netConnect } from 'node:net';
import { createClient } from 'rivetkit/client';
import type { Registry } from './registry.ts';

export interface ServerOptions {
  readonly enginePort: number;
  readonly engineVersion: string;
  readonly homeDir: string;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Spawn the standalone actor server as a child (so it can be truly killed). */
export function spawnServer(opts: ServerOptions): ChildProcess {
  return spawn('bun', ['run', 'src/server.ts'], {
    env: {
      ...process.env,
      HOME: opts.homeDir,
      SPIKE_ENGINE_PORT: String(opts.enginePort),
      SPIKE_ENGINE_VERSION: opts.engineVersion,
    },
    stdio: 'inherit',
  });
}

/** Kill any local engine by exact process name (the server never respawns it). */
export function killEngine(): Promise<void> {
  return new Promise((resolve) => {
    const proc = spawn('pkill', ['-x', 'rivet-engine']);
    proc.on('exit', () => resolve());
    proc.on('error', () => resolve());
  });
}

/** Kill the server child and the engine it spawned; both must die for a cold restart. */
export async function stopServer(server: ChildProcess): Promise<void> {
  server.kill('SIGKILL');
  await killEngine();
  await delay(1500);
}

/** True once nothing is listening on `port`. */
export function portFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = netConnect({ host: '127.0.0.1', port });
    socket.once('connect', () => {
      socket.destroy();
      resolve(false);
    });
    socket.once('error', () => resolve(true));
    socket.setTimeout(1000, () => {
      socket.destroy();
      resolve(true);
    });
  });
}

export async function waitPortFree(port: number): Promise<void> {
  for (let i = 0; i < 40; i++) {
    if (await portFree(port)) {
      return;
    }
    await delay(500);
  }
  throw new Error(`port ${port} never freed`);
}

/** Poll an actor action until the freshly-booted server can serve it. */
export async function waitForReady(endpoint: string, timeoutMs = 30000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown;
  while (Date.now() < deadline) {
    try {
      const conn = createClient<Registry>(endpoint).conversation.getOrCreate(['ready-probe']).connect();
      await conn.getTranscript();
      await conn.dispose();
      return;
    } catch (error) {
      lastError = error;
      await delay(500);
    }
  }
  throw new Error(`server not ready: ${String(lastError)}`);
}
