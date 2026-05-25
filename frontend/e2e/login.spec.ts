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
	test('dev-login + provisioned workspace lands on the home shell', async ({ page, context }) => {
		const backend = process.env.E2E_API_URL ?? 'http://localhost:8000';
		// ``context.request`` shares cookies with the browser context, so
		// the dev-login session carries into the personalization upsert.
		const loginResponse = await context.request.post(`${backend}/auth/dev-login`);
		expect(loginResponse.ok()).toBe(true);
		// The home shell only renders once the user has a provisioned
		// workspace (see ``useOnboardingReadiness`` + ``AppShell``).
		// Trigger the personalization upsert so onboarding-status reports
		// has_workspace_ready=true before we navigate.
		const provisionResponse = await context.request.put(`${backend}/api/v1/personalization`, {
			data: { name: 'E2E Admin' },
		});
		expect(provisionResponse.ok()).toBe(true);

		await page.goto('/');
		// The chat composer is visible from the home page once authenticated.
		await expect(
			page.getByPlaceholder(/^(Ask|Type|Send)/i).or(page.getByRole('textbox'))
		).toBeVisible();
	});
});
