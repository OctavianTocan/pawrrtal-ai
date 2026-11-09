/**
 * M6 — the actor server in the production "standalone" shape.
 *
 * M1–M5 booted the runtime via `rivetkit/test`'s `setupTest`, which spawns the
 * engine implicitly and needs a runner-readiness retry. This module owns the
 * engine lifecycle explicitly the way a deployed pod would:
 *   - `startEngine: true` spawns the engine,
 *   - `engineVersion` + `envoy.version` pin a STABLE runner version (the M2
 *     durability knob, here as config instead of the `RIVET_ENVOY_VERSION` env
 *     hack), and
 *   - `registry.start()` runs the actor envoy and keeps the process alive.
 *
 * Killing this process (and the engine it spawned) is a real cold restart.
 *
 * NB (rivetkit 2.3.2): the reference's `serverless.{spawnEngine,
 * configureRunnerPool}` is superseded by top-level `startEngine` +
 * `engine*`/`envoy`. `configurePool` is only for the serverless HTTP-callback
 * pool (Mode B); the in-process envoy here needs no callback URL.
 */
import { setup } from 'rivetkit';
import { conversation } from './conversation-actor.ts';

const ENGINE_PORT = Number(process.env.SPIKE_ENGINE_PORT ?? 6420);
const ENGINE_VERSION = process.env.SPIKE_ENGINE_VERSION ?? '1';

const registry = setup({
  use: { conversation },
  startEngine: true,
  enginePort: ENGINE_PORT,
  engineVersion: ENGINE_VERSION,
  envoy: { version: Number(ENGINE_VERSION), totalSlots: 16 },
});

registry.start();
process.stdout.write(`[server] envoy started; engine :${ENGINE_PORT} version=${ENGINE_VERSION}\n`);
