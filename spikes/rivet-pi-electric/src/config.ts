/**
 * M3 spike endpoints. These point at the throwaway docker-compose stack in
 * `infra/docker-compose.yml` (isolated, loopback-only ports so they don't
 * collide with the host's other Postgres instances).
 */

/** Postgres the API writes to (the single-writer store). */
export const PG_URL = process.env.SPIKE_PG_URL ?? 'postgresql://postgres:postgres@127.0.0.1:5499/app';

/** Electric sync service the read-path clients subscribe to. */
export const ELECTRIC_URL = process.env.SPIKE_ELECTRIC_URL ?? 'http://127.0.0.1:5599';

/** Identity-scoped gatekeeper proxy that sits in front of Electric (M4). */
export const PROXY_PORT = Number(process.env.SPIKE_PROXY_PORT ?? 5699);
export const PROXY_URL = process.env.SPIKE_PROXY_URL ?? `http://127.0.0.1:${PROXY_PORT}`;
