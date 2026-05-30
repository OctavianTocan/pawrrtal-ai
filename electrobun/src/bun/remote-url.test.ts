import { describe, expect, it } from 'vitest';
import { resolveRemoteAppUrl } from './remote-url';

describe('resolveRemoteAppUrl', () => {
	it('accepts an https origin', () => {
		expect(resolveRemoteAppUrl('https://pawrrtal.example.ts.net/app')).toBe(
			'https://pawrrtal.example.ts.net'
		);
	});

	it('defaults scheme-less hosts to https', () => {
		expect(resolveRemoteAppUrl('pawrrtal.example.ts.net')).toBe(
			'https://pawrrtal.example.ts.net'
		);
	});

	it('rejects malformed values with a clear error', () => {
		expect(() => resolveRemoteAppUrl('https://bad host')).toThrow(
			'PAWRRTAL_REMOTE_URL must be a valid https:// URL or host.'
		);
	});

	it.each([
		'http://example.com',
		'localhost',
		'app.localhost',
		'127.0.0.1',
		'127.8.9.10',
		'[::1]',
	])('rejects unsafe remote URL %s', (value) => {
		expect(() => resolveRemoteAppUrl(value)).toThrow(/PAWRRTAL_REMOTE_URL/);
	});
});
