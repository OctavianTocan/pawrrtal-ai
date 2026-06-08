import { describe, expect, it } from 'vitest';
import { backendRewriteRules } from './next.backend-rewrites';

describe('next.config backend rewrites', (): void => {
	it('proxies browser auth, user, and API paths to the backend origin', async (): Promise<void> => {
		const rewrites = backendRewriteRules({
			NODE_ENV: 'development',
			BACKEND_INTERNAL_URL: 'http://127.0.0.1:18001/',
		});

		expect(rewrites).toContainEqual({
			source: '/auth/:path*',
			destination: 'http://127.0.0.1:18001/auth/:path*',
		});
		expect(rewrites).toContainEqual({
			source: '/users/:path*',
			destination: 'http://127.0.0.1:18001/users/:path*',
		});
		expect(rewrites).toContainEqual({
			source: '/api/v1/:path*',
			destination: 'http://127.0.0.1:18001/api/v1/:path*',
		});
	});
});
