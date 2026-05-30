import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('buildServerApiUrl', (): void => {
	beforeEach((): void => {
		vi.resetModules();
		vi.unstubAllEnvs();
	});

	it('uses BACKEND_INTERNAL_URL when configured', async (): Promise<void> => {
		vi.stubEnv('BACKEND_INTERNAL_URL', 'http://127.0.0.1:8000');
		const { buildServerApiUrl } = await import('./server-api-url');

		expect(buildServerApiUrl('/api/v1/health')).toBe('http://127.0.0.1:8000/api/v1/health');
	});

	it('falls back to the legacy public API URL for existing deployments', async (): Promise<void> => {
		vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.example.com');
		const { buildServerApiUrl } = await import('./server-api-url');

		expect(buildServerApiUrl('/api/v1/health')).toBe('https://api.example.com/api/v1/health');
	});
});
