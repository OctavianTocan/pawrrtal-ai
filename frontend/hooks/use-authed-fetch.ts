'use client';

import { useRouter } from 'next/navigation';
import { useCallback } from 'react';
import { apiFetch } from '@/lib/api';

/**
 * Returns a memoized same-origin `fetch` wrapper that sends cookies and handles auth failures.
 *
 * - Uses {@link apiFetch} so API path normalization stays consistent.
 * - Sends `credentials: 'include'` so the HTTP-only session cookie reaches the API.
 * - On `401`, replaces the route with `/login` and throws (callers should treat this as a hard logout signal).
 * - On other non-OK responses, throws with status and body text for debugging.
 *
 * @returns Async function `(endpoint, options?) => Response` where `endpoint` is a path string or lazy path factory.
 */
export function useAuthedFetch() {
	const router = useRouter();

	// Return a stable function identity between renders so effects depending on it do not loop.
	return useCallback(
		async function authedFetch(endpoint: string | (() => string), options?: RequestInit) {
			const path = typeof endpoint === 'function' ? endpoint() : endpoint;

			// apiFetch normalizes browser API paths and keeps same-origin routing consistent.
			const response = await apiFetch(path, {
				...options,
				// Include the session token in the request. (HTTPOnly Cookie)
				credentials: 'include',
				cache: 'no-store',
			});

			// Handle expired cookies. (User is not authenticated.)
			if (response.status === 401) {
				// Preserve where the user was so the login page can return
				// them after a fresh sign-in. Matches the same ``?redirect=``
				// param the Next.js middleware (``frontend/middleware.ts``)
				// sets when no cookie is present in the first place.
				if (typeof window !== 'undefined') {
					const target = window.location.pathname + window.location.search;
					router.replace(`/login?redirect=${encodeURIComponent(target)}`);
				} else {
					router.replace('/login');
				}
				throw new Error('User is not authenticated');
			}

			// Handle other errors.
			if (!response.ok) {
				throw new Error(
					`API Error: ${response.status} ${response.statusText}. Body: ${await response.text()}`
				);
			}

			// Return the user.
			return response;
		},
		[router]
	);
}
