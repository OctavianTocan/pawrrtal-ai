/**
 * Effect v4 API entrypoint (strangler on :8001). Handlers and server bootstrap
 * land here; see effect-smol `ai-docs/src/51_http-server/10_basics.ts`.
 */
import { Effect } from 'effect';
import './Main.ts';

/** Proves vendor `file:` wiring resolves for `bun run typecheck`. */
export const ready = Effect.void;
