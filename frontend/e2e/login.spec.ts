/**
 * Login + dev-admin shortcut smoke tests.
 *
 * Asserts the login page renders the expected affordances (email +
 * password fields, Login + SSO buttons, dev-admin shortcut on non-prod)
 * and proves the dev-admin button signs in through the browser path. Does
 * NOT exercise the OAuth handshakes — those go to external providers and
 * aren't appropriate for the smoke suite.
 */

import { devices } from '@playwright/test';
import { expect, test } from './fixtures';

const mobileLoginDevice = {
	deviceScaleFactor: devices['iPhone 13'].deviceScaleFactor,
	hasTouch: devices['iPhone 13'].hasTouch,
	isMobile: devices['iPhone 13'].isMobile,
	userAgent: devices['iPhone 13'].userAgent,
	viewport: devices['iPhone 13'].viewport,
};

test.describe('login page', () => {
	test('renders email + password fields and the SSO buttons', async ({ page }) => {
		await page.goto('/login');
		await expect(page.getByLabel('Email')).toBeVisible();
		await expect(page.getByLabel('Password')).toBeVisible();
		await expect(page.getByRole('button', { name: 'Login' })).toBeVisible();
		await expect(page.getByRole('button', { name: /Continue with Google/i })).toBeVisible();
		await expect(page.getByRole('button', { name: /Continue with Apple/i })).toBeVisible();
	});

	test('shows the dev-admin shortcut on non-production deploys', async ({ page }) => {
		await page.goto('/login');
		await expect(page.getByRole('button', { name: 'Dev Admin' })).toBeVisible();
	});

	test('dev-admin shortcut signs in through the UI path', async ({ page }) => {
		await page.goto('/login');
		const devLoginResponse = page.waitForResponse(
			(response) =>
				response.url().includes('/auth/dev-login') && response.request().method() === 'POST'
		);

		await page.getByRole('button', { name: 'Dev Admin' }).click();

		expect((await devLoginResponse).ok()).toBe(true);
		await expect(page).toHaveURL(/\/$/);

		const isAuthenticated = await page.evaluate(async () => {
			const response = await fetch('/api/v1/users/me', { credentials: 'include' });
			return response.ok;
		});
		expect(isAuthenticated).toBe(true);
	});
});

test.describe('mobile login page', () => {
	test.use(mobileLoginDevice);

	test('dev-admin shortcut signs in from a touch tap', async ({ page }) => {
		await page.goto('/login');
		const devLoginResponse = page.waitForResponse(
			(response) =>
				response.url().includes('/auth/dev-login') && response.request().method() === 'POST'
		);

		await page.getByRole('button', { name: 'Dev Admin' }).tap();

		expect([204, 303]).toContain((await devLoginResponse).status());
		await expect(page).toHaveURL(/\/$/);

		const isAuthenticated = await page.evaluate(async () => {
			const response = await fetch('/api/v1/users/me', { credentials: 'include' });
			return response.ok;
		});
		expect(isAuthenticated).toBe(true);
	});
});

test.describe('authenticated landing', () => {
	test('dev-login + provisioned workspace lands on the home shell', async ({
		page,
		authenticatedPageWithWorkspace,
	}) => {
		void authenticatedPageWithWorkspace;

		await page.goto('/');
		// The chat composer is visible from the home page once authenticated.
		await expect(page.getByRole('textbox', { name: /Ask Pawrrtal/i })).toBeVisible();
	});
});
