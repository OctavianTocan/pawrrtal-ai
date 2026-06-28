/**
 * The trusted identity authority (M5).
 *
 * Stands in for what the reference does over RPC: the electric-proxy forwards
 * the caller's credential headers to the main API, which validates them and
 * returns the identity (`backend/vendor/effect-api-layout/apps/electric-proxy/
 * src/Modules/Authentication/Services/Auth.ts`). In production this is the
 * Python `GET :8000/users/me` / Session-in-Effect lookup.
 *
 * Here it is an in-memory map: a session id resolves to an owner, or to nothing
 * (unknown/forged/expired). The point of M5 is that the proxy derives identity
 * from THIS authority, never from a client-asserted value.
 */
import { randomUUID } from 'node:crypto';

export interface SessionStore {
  /** Mint a session for `owner`; returns the opaque session id. */
  create(owner: string): string;
  /** Resolve a session id to its owner, or `null` if unknown/revoked. */
  lookup(sessionId: string): string | null;
  /** Invalidate a session (e.g. logout); subsequent lookups return `null`. */
  revoke(sessionId: string): void;
}

/** Build an in-memory session store. */
export function createSessionStore(): SessionStore {
  const sessions = new Map<string, string>();
  return {
    create(owner: string): string {
      const sessionId = randomUUID();
      sessions.set(sessionId, owner);
      return sessionId;
    },
    lookup(sessionId: string): string | null {
      return sessions.get(sessionId) ?? null;
    },
    revoke(sessionId: string): void {
      sessions.delete(sessionId);
    },
  };
}
