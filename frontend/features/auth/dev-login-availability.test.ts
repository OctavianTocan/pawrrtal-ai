import { describe, expect, it } from 'vitest';
import { canUseDevAdminLogin } from './dev-login-availability';

describe('canUseDevAdminLogin', () => {
	it('shows the shortcut in next dev by default', () => {
		expect(canUseDevAdminLogin({ NODE_ENV: 'development' })).toBe(true);
	});

	it('hides the shortcut in production by default', () => {
		expect(canUseDevAdminLogin({ NODE_ENV: 'production' })).toBe(false);
	});

	it('allows production deployments to opt in explicitly', () => {
		expect(
			canUseDevAdminLogin({
				NODE_ENV: 'production',
				PAWRRTAL_ENABLE_DEV_LOGIN: 'true',
			})
		).toBe(true);
		expect(
			canUseDevAdminLogin({
				NODE_ENV: 'production',
				PAWRRTAL_ENABLE_DEV_LOGIN: '1',
			})
		).toBe(true);
	});

	it('lets the explicit flag disable the shortcut in development', () => {
		expect(
			canUseDevAdminLogin({
				NODE_ENV: 'development',
				PAWRRTAL_ENABLE_DEV_LOGIN: 'false',
			})
		).toBe(false);
	});
});
