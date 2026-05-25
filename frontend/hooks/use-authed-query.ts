import { type QueryKey, useQuery } from '@tanstack/react-query';
import { useAuthedFetch } from './use-authed-fetch';

export interface UseAuthedQueryOptions {
	/**
	 * When `false` the query is skipped entirely.  Mirrors the React Query
	 * `enabled` flag — useful for dependent queries where the URL is not yet
	 * known.
	 *
	 * @default true
	 */
	enabled?: boolean;
	/** Stale time in milliseconds passed through to React Query. */
	staleTime?: number;
	/** Poll interval in ms. When set, the query refetches automatically. */
	refetchInterval?: number;
}

/**
 * `useQuery` bound to {@link useAuthedFetch}: JSON GET with cookie auth and shared 401 handling.
 *
 * @typeParam T - Parsed JSON type of the response body.
 * @param queryKey - React Query cache key (include all values that should invalidate the fetch).
 * @param endpoint - API path appended to the configured backend origin (see `lib/api.ts`).
 * @param options  - Optional React Query overrides (`enabled`, `staleTime`).
 */
export function useAuthedQuery<T>(
	queryKey: QueryKey,
	endpoint: string,
	options?: UseAuthedQueryOptions
) {
	const authedFetch = useAuthedFetch();
	return useQuery<T>({
		queryKey,
		queryFn: async () => {
			const response = await authedFetch(endpoint);
			return response.json();
		},
		enabled: options?.enabled,
		staleTime: options?.staleTime,
		refetchInterval: options?.refetchInterval,
	});
}
