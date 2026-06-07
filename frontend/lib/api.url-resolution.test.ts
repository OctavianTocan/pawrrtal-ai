import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('apiFetch URL resolution', (): void => {
	beforeEach((): void => {
		vi.resetModules();
		vi.unstubAllEnvs();
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('ok')));
	});

	it('uses same-origin paths for versioned API routes', async (): Promise<void> => {
		const { apiFetch } = await import('./api');

		await apiFetch('/api/v1/health');

		expect(fetch).toHaveBeenCalledWith('/api/v1/health', undefined);
	});

	it('uses same-origin paths for auth routes', async (): Promise<void> => {
		const { apiFetch } = await import('./api');

		await apiFetch('/auth/dev-login', { method: 'POST' });

		expect(fetch).toHaveBeenCalledWith('/auth/dev-login', { method: 'POST' });
	});

	it('normalizes relative paths to a leading slash', async (): Promise<void> => {
		const { apiFetch } = await import('./api');

		await apiFetch('users/me');

		expect(fetch).toHaveBeenCalledWith('/users/me', undefined);
	});

	it('leaves explicit absolute URLs untouched', async (): Promise<void> => {
		const { getBrowserApiUrl } = await import('./api');

		expect(getBrowserApiUrl('https://example.test/api/v1/health')).toBe(
			'https://example.test/api/v1/health'
		);
	});
});
