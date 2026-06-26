/**
 * Singleton React Query client factory for App Router.
 *
 * @fileoverview Server requests get a fresh client per render; the browser reuses one instance across navigations.
 */

import { isServer, QueryClient } from '@tanstack/react-query';

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // SSR tip: avoid immediate client refetch after hydration
        staleTime: 60 * 1000,
        gcTime: 60 * 30 * 1000,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

/**
 * Returns the appropriate `QueryClient` for the current runtime (RSC vs browser).
 */
export function getQueryClient() {
  if (isServer) {
    return makeQueryClient();
  }
  if (!browserQueryClient) browserQueryClient = makeQueryClient();
  return browserQueryClient;
}
