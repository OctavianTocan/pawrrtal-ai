import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('apiFetch URL resolution', (): void => {
	const originalLocation = window.location;

	beforeEach((): void => {
		vi.resetModules();
		vi.unstubAllEnvs();
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('ok')));
		window.localStorage.clear();
		Object.defineProperty(window, 'location', {
			configurable: true,
			value: originalLocation,
		});
	});

	it('uses relative paths when the browser API base is same-origin', async (): Promise<void> => {
		vi.stubEnv('NEXT_PUBLIC_BROWSER_API_BASE', '');
		const { apiFetch } = await import('./api');

		await apiFetch('/api/v1/health');

		expect(fetch).toHaveBeenCalledWith('/api/v1/health', undefined);
	});

	it('treats explicit same-origin browser config as configured', async (): Promise<void> => {
		vi.stubEnv('NEXT_PUBLIC_BROWSER_API_BASE', '');
		const { hasBackendConfig, saveBackendConfig } = await import('./api');

		saveBackendConfig({ url: window.location.origin, apiKey: '' });
		expect(hasBackendConfig()).toBe(true);
	});

	it('does not treat the implicit localhost fallback as configured', async (): Promise<void> => {
		const { hasBackendConfig } = await import('./api');

		expect(hasBackendConfig()).toBe(false);
	});

	it('keeps legacy absolute local defaults when no same-origin base is configured', async (): Promise<void> => {
		vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://localhost:8000');
		const { apiFetch } = await import('./api');

		await apiFetch('/api/v1/health');

		expect(fetch).toHaveBeenCalledWith('http://localhost:8000/api/v1/health', undefined);
	});

	it('uses same-origin proxy paths on Tailscale dev origins', async (): Promise<void> => {
		Object.defineProperty(window, 'location', {
			configurable: true,
			value: new URL('https://openclaw-vps.tailb0501a.ts.net:7447/login'),
		});
		const { apiFetch } = await import('./api');

		await apiFetch('/auth/dev-login', { method: 'POST' });

		expect(fetch).toHaveBeenCalledWith('/auth/dev-login', { method: 'POST' });
	});

	it('returns a browser-reachable hosted config URL on Tailscale dev origins', async (): Promise<void> => {
		Object.defineProperty(window, 'location', {
			configurable: true,
			value: new URL('https://openclaw-vps.tailb0501a.ts.net:7447/login'),
		});
		vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://localhost:8000');
		const { getHostedBackendConfigUrl } = await import('./api');

		expect(getHostedBackendConfigUrl()).toBe('https://openclaw-vps.tailb0501a.ts.net:7447');
	});

	it('heals no-key localhost backend overrides on Tailscale dev origins', async (): Promise<void> => {
		Object.defineProperty(window, 'location', {
			configurable: true,
			value: new URL('https://openclaw-vps.tailb0501a.ts.net:7447/login'),
		});
		const { apiFetch, saveBackendConfig } = await import('./api');
		saveBackendConfig({ url: 'http://127.0.0.1:8001', apiKey: '' });

		await apiFetch('/auth/dev-login', { method: 'POST' });

		expect(window.localStorage.getItem('pawrrtal:backend-config')).toBe(
			JSON.stringify({ url: 'https://openclaw-vps.tailb0501a.ts.net:7447', apiKey: '' })
		);
		expect(fetch).toHaveBeenCalledWith('https://openclaw-vps.tailb0501a.ts.net:7447/auth/dev-login', {
			method: 'POST',
		});
	});
});
