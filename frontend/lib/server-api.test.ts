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

	it('defaults to the local backend origin', async (): Promise<void> => {
		const { buildServerApiUrl } = await import('./server-api-url');

		expect(buildServerApiUrl('/api/v1/health')).toBe('http://127.0.0.1:8000/api/v1/health');
	});
});
