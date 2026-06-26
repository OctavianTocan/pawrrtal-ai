import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

/** Creates a React Query client configured for deterministic tests. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

/** Creates a React component wrapper that provides a test QueryClient. */
export function createQueryClientWrapper(
  queryClient: QueryClient = createTestQueryClient()
): (props: PropsWithChildren) => React.JSX.Element {
  return function TestQueryClientWrapper({ children }: PropsWithChildren): React.JSX.Element {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}
