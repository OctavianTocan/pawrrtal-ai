/**
 * Login + dev-admin shortcut smoke tests.
 *
 * Asserts the login page renders the expected affordances (email +
 * password fields, Login + SSO buttons, dev-admin shortcut on
 * non-prod). Does NOT exercise the OAuth handshakes — those go to
 * external providers and aren't appropriate for the smoke suite.
 */

import { expect, test } from './fixtures';

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
});

test.describe('authenticated landing', () => {
	test('dev-login lands on the home shell', async ({ page, context }) => {
		const response = await context.request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/auth/dev-login`
		);
		expect(response.ok()).toBe(true);
		await page.goto('/');
		// The sidebar "New Session" button confirms the authenticated shell loaded.
		await expect(page.getByRole('button', { name: /New Session/i })).toBeVisible();
		// The chat surface renders its empty-state heading.
		await expect(page.getByText(/What should we build/i)).toBeVisible();
	});
});
