/**
 * The identity-scoped Electric gatekeeper (M4).
 *
 * Mirrors `backend/vendor/effect-api-layout/apps/electric-proxy` (trimmed to
 * plain TS): authenticate → validate the table → forward ONLY recognized
 * Electric protocol params (offset/handle/live/cursor/…) → server-force the
 * `table`, a `columns` allowlist, and an owner-scoped parameterized `where`
 * → stream the upstream response back.
 *
 * The security property: a client can NOT widen its view. Any client-supplied
 * `where`/`table`/`columns` are dropped (they aren't protocol params), and the
 * only filter that reaches Electric is the proxy's `owner = $1` bound to the
 * authenticated identity. This is the read-path half of "single writer +
 * per-identity scoped sync" that files-first could never enforce centrally.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import { ELECTRIC_PROTOCOL_QUERY_PARAMS } from '@electric-sql/client';
import { ELECTRIC_URL } from './config.ts';
import type { SessionStore } from './session-store.ts';

/** Per-table column allowlist; the client's requested columns are ignored. */
const ALLOWED_COLUMNS: Record<string, readonly string[]> = {
  conversations: ['id', 'owner', 'title', 'last_message', 'turn_count', 'updated_at'],
};

const PROTOCOL_PARAMS = new Set<string>(ELECTRIC_PROTOCOL_QUERY_PARAMS);
const HOP_BY_HOP = ['content-encoding', 'content-length', 'transfer-encoding', 'connection'];

/**
 * Resolves the authenticated owner for a request, or `null` to reject (401).
 * This is the seam where real identity plugs in: it must derive the owner from
 * something the server trusts, never from a client-asserted value.
 */
export type ProxyAuth = (req: IncomingMessage) => string | null;

/**
 * M4 authenticator: trust an `x-spike-user` header. Fine for proving the scope
 * mechanism, but NOT safe for real clients — the caller asserts its own
 * identity. Superseded by `sessionAuth` (M5).
 */
export const headerAuth: ProxyAuth = (req) => {
  const header = req.headers['x-spike-user'];
  return (Array.isArray(header) ? header[0] : header) ?? null;
};

/** Pull a session id from `Authorization: Bearer <id>` or `Cookie: session=<id>`. */
function extractSessionId(req: IncomingMessage): string | null {
  const authHeader = req.headers.authorization;
  const auth = Array.isArray(authHeader) ? authHeader[0] : authHeader;
  if (auth?.startsWith('Bearer ')) {
    return auth.slice('Bearer '.length).trim() || null;
  }
  const cookieHeader = req.headers.cookie;
  const cookie = Array.isArray(cookieHeader) ? cookieHeader[0] : cookieHeader;
  if (cookie) {
    for (const part of cookie.split(';')) {
      const [name, ...rest] = part.trim().split('=');
      if (name === 'session') {
        return rest.join('=') || null;
      }
    }
  }
  return null;
}

/**
 * M5 authenticator: resolve identity through the trusted {@link SessionStore}.
 * A client-asserted header is ignored entirely — only a validated session id
 * (from `Authorization`/`Cookie`) yields an owner; unknown/forged → reject.
 */
export function sessionAuth(store: SessionStore): ProxyAuth {
  return (req) => {
    const sessionId = extractSessionId(req);
    if (!sessionId) {
      return null;
    }
    return store.lookup(sessionId);
  };
}

/** Start the gatekeeper proxy on `port` (loopback only). */
export function startProxy(port: number, authenticate: ProxyAuth = headerAuth): Server {
  const server = createServer((req, res) => {
    handle(req, res, port, authenticate).catch((error) => {
      if (!res.headersSent) {
        res.writeHead(500, { 'content-type': 'application/json' });
      }
      res.end(JSON.stringify({ error: 'proxy_internal', detail: String(error) }));
    });
  });
  server.listen(port, '127.0.0.1');
  return server;
}

function deny(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'content-type': 'application/json' });
  res.end(JSON.stringify(body));
}

/** Abort the upstream fetch when the downstream client disconnects. */
function abortSignalFor(req: IncomingMessage): AbortSignal {
  const controller = new AbortController();
  req.on('close', () => controller.abort());
  return controller.signal;
}

async function handle(req: IncomingMessage, res: ServerResponse, port: number, authenticate: ProxyAuth): Promise<void> {
  const url = new URL(req.url ?? '/', `http://127.0.0.1:${port}`);
  if (url.pathname !== '/v1/shape') {
    return deny(res, 404, { error: 'not_found' });
  }
  if (req.method !== 'GET' && req.method !== 'DELETE') {
    return deny(res, 405, { error: 'method_not_allowed' });
  }

  // 1. Identity — resolved by the configured authenticator (a validated session
  //    in production), never trusted from a client-asserted value.
  const owner = authenticate(req);
  if (!owner) {
    return deny(res, 401, { error: 'missing or invalid identity' });
  }

  // 2. Table allowlist (also drives the column allowlist).
  const table = url.searchParams.get('table');
  if (!table) {
    return deny(res, 400, { error: 'missing table' });
  }
  const columns = ALLOWED_COLUMNS[table];
  if (!columns) {
    return deny(res, 403, { error: `table "${table}" is not allowed for sync` });
  }

  // 3. Forward ONLY recognized Electric protocol params from the client.
  const upstream = new URL(`${ELECTRIC_URL}/v1/shape`);
  for (const [key, value] of url.searchParams.entries()) {
    if (PROTOCOL_PARAMS.has(key)) {
      upstream.searchParams.set(key, value);
    }
  }

  // 4. Server forces table + columns + owner-scoped where (client can't override).
  upstream.searchParams.set('table', table);
  upstream.searchParams.set('columns', columns.join(','));
  upstream.searchParams.set('where', 'owner = $1');
  const upstreamUrl = `${upstream.toString()}&params[1]=${encodeURIComponent(owner)}`;

  // 5. Forward and stream the response back.
  const upstreamRes = await fetch(upstreamUrl, { signal: abortSignalFor(req) });
  const headers: Record<string, string> = {};
  upstreamRes.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.includes(key.toLowerCase())) {
      headers[key] = value;
    }
  });
  headers['cache-control'] = 'private, no-store';
  res.writeHead(upstreamRes.status, headers);

  if (!upstreamRes.body) {
    res.end();
    return;
  }
  const reader = upstreamRes.body.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    if (value) {
      res.write(value);
    }
  }
  res.end();
}
