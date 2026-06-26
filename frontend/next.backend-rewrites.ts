const DEFAULT_BACKEND_INTERNAL_URL = 'http://127.0.0.1:8000';

/**
 * Server-side rewrite from a public Next.js path to the internal backend origin.
 */
export interface BackendRewriteRule {
  /** Incoming Next.js source path pattern. */
  source: string;
  /** Backend destination URL or path pattern. */
  destination: string;
}

interface BackendRewriteEnv {
  BACKEND_INTERNAL_URL?: string;
  NEXT_ENABLE_BACKEND_REWRITES?: string;
  NODE_ENV?: string;
}

function backendRewritesEnabled(env: BackendRewriteEnv): boolean {
  return env.NODE_ENV !== 'production' || Boolean(env.BACKEND_INTERNAL_URL) || env.NEXT_ENABLE_BACKEND_REWRITES === '1';
}

/**
 * Builds the backend rewrite rules used by Next.js server requests.
 *
 * @param env - Environment values to read. Defaults to `process.env`.
 * @returns Rewrite rules for backend-owned paths, or an empty list when disabled.
 *
 * @example
 * ```ts
 * rewrites: async () => backendRewriteRules()
 * ```
 */
export function backendRewriteRules(env: BackendRewriteEnv = process.env): BackendRewriteRule[] {
  if (!backendRewritesEnabled(env)) {
    return [];
  }

  const destinationBase = (env.BACKEND_INTERNAL_URL ?? DEFAULT_BACKEND_INTERNAL_URL).replace(/\/$/, '');

  return [
    {
      source: '/api/v1/:path*',
      destination: `${destinationBase}/api/v1/:path*`,
    },
    {
      source: '/auth/:path*',
      destination: `${destinationBase}/auth/:path*`,
    },
    {
      source: '/users/:path*',
      destination: `${destinationBase}/users/:path*`,
    },
  ];
}
