/**
 * Shared in-process boot helper for the spike.
 *
 * rivetkit's `setupTest` spawns the native engine and waits for its `/metadata`
 * endpoint, but NOT for the in-process runner pool to finish registering. The
 * first actor call therefore races runner registration and intermittently fails
 * with `no_runner_config_configured`. `bootConversation` papers over that race
 * by retrying the first (idempotent) actor call until the runner is ready, then
 * hands back a live connection. This is a spike-harness concern, not a Pawrrtal
 * runtime concern.
 */
import { setupTest } from 'rivetkit/test';
import { registry } from './registry.ts';

type Finalizer = () => void | Promise<void>;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRunnerNotReady(error: unknown): boolean {
  return String(error).includes('no_runner_config_configured');
}

/** Boot the runtime + client and return a connection once the runner is ready. */
export async function bootConversation(key: string[]): Promise<{
  // biome-ignore lint/suspicious/noExplicitAny: rivetkit conn type is deeply generic; spike-local
  conn: any;
  cleanup: () => Promise<void>;
}> {
  const finalizers: Finalizer[] = [];
  const testCtx = { onTestFinished: (fn: Finalizer) => finalizers.push(fn) };
  // biome-ignore lint/suspicious/noExplicitAny: stub vitest TestContext for the harness
  const { client } = await setupTest(testCtx as any, registry);

  const attempts = 40;
  const delayMs = 250;
  let lastError: unknown;
  // biome-ignore lint/suspicious/noExplicitAny: spike-local conn handle
  let ready: any;
  for (let i = 0; i < attempts; i++) {
    const conn = client.conversation.getOrCreate(key).connect();
    try {
      await conn.getTranscript();
      ready = conn;
      break;
    } catch (error) {
      lastError = error;
      try {
        await conn.dispose();
      } catch {
        // ignore dispose failures on a connection that never opened
      }
      if (!isRunnerNotReady(error)) {
        throw error;
      }
      await sleep(delayMs);
    }
  }
  if (!ready) {
    throw lastError;
  }

  const cleanup = async (): Promise<void> => {
    try {
      await ready.dispose();
    } catch {
      // ignore
    }
    for (const fn of finalizers) {
      try {
        await fn();
      } catch {
        // ignore
      }
    }
    try {
      await registry.shutdown();
    } catch {
      // ignore
    }
  };

  return { conn: ready, cleanup };
}
