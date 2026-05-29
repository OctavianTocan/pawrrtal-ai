import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthedFetch } from './use-authed-fetch';

const replaceMock = vi.fn();
const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

vi.mock('next/navigation', () => ({
	useRouter: () => ({
		replace: replaceMock,
	}),
}));

describe('useAuthedFetch', (): void => {
	beforeEach((): void => {
		replaceMock.mockClear();
		vi.stubGlobal('fetch', vi.fn());
	});

	it('prefixes API URLs and includes credentials', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(new Response('ok'));

		const { result } = renderHook(() => useAuthedFetch());

		await result.current('/api/v1/conversations', {
			method: 'GET',
		});

		expect(fetch).toHaveBeenCalledWith(`${apiBaseUrl}/api/v1/conversations`, {
			method: 'GET',
			credentials: 'include',
			cache: 'no-store',
		});
	});

	it('redirects to /login with ?redirect= and throws on 401 responses', async (): Promise<void> => {
		// On a 401 the hook must preserve where the user was so the login
		// page can return them after re-authenticating — same contract the
		// Next.js proxy (``frontend/proxy.ts``) uses when no cookie is
		// present in the first place.
		vi.mocked(fetch).mockResolvedValue(new Response('nope', { status: 401 }));

		const { result } = renderHook(() => useAuthedFetch());

		await expect(result.current('/me')).rejects.toThrow('User is not authenticated');
		expect(replaceMock).toHaveBeenCalledOnce();
		// Must point at /login and round-trip the original path through ?redirect=.
		expect(replaceMock).toHaveBeenCalledWith(expect.stringMatching(/^\/login\?redirect=/));
	});

	it('includes response bodies in non-auth API errors', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(new Response('broken database', { status: 500 }));

		const { result } = renderHook(() => useAuthedFetch());

		await expect(result.current('/api/v1/conversations')).rejects.toThrow(
			'API Error: 500 . Body: broken database'
		);
	});
});
