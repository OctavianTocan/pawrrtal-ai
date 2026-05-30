import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('apiFetch URL resolution', (): void => {
	beforeEach((): void => {
		vi.resetModules();
		vi.unstubAllEnvs();
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('ok')));
		window.localStorage.clear();
	});

	it('uses relative paths when the browser API base is same-origin', async (): Promise<void> => {
		vi.stubEnv('NEXT_PUBLIC_BROWSER_API_BASE', '');
		const { apiFetch } = await import('./api');

		await apiFetch('/api/v1/health');

		expect(fetch).toHaveBeenCalledWith('/api/v1/health', undefined);
	});

	it('treats same-origin browser API defaults as configured', async (): Promise<void> => {
		vi.stubEnv('NEXT_PUBLIC_BROWSER_API_BASE', '');
		const { hasBackendConfig } = await import('./api');

		expect(hasBackendConfig()).toBe(true);
	});

	it('keeps legacy absolute local defaults when no same-origin base is configured', async (): Promise<void> => {
		vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://localhost:8000');
		const { apiFetch } = await import('./api');

		await apiFetch('/api/v1/health');

		expect(fetch).toHaveBeenCalledWith('http://localhost:8000/api/v1/health', undefined);
	});
});
