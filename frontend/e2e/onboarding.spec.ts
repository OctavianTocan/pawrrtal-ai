/**
 * Onboarding wizard smoke: without a backend config in localStorage,
 * AppShell dispatches the server-step event on mount, opening the
 * wizard at the "Where is your Pawrrtal?" step. We verify the wizard
 * opens and the Continue button advances to the next step.
 */

import { expect, test } from './fixtures';

test.use({ skipOnboarding: false });

test.describe('onboarding wizard', () => {
	test.beforeEach(async ({ context }) => {
		const response = await context.request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/auth/dev-login`
		);
		expect(response.ok()).toBe(true);
	});

	test('renders the server selection step on fresh load', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByRole('heading', { name: /Where is your Pawrrtal/i })).toBeVisible({
			timeout: 10_000,
		});
		await expect(page.getByText(/Hosted by Pawrrtal/i)).toBeVisible();
		await expect(page.getByText(/Self-hosted/i)).toBeVisible();
	});

	test('Continue button progresses to the next step', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByRole('heading', { name: /Where is your Pawrrtal/i })).toBeVisible({
			timeout: 10_000,
		});
		await page
			.getByRole('button', { name: /Continue/i })
			.first()
			.click();
		// After server step, the wizard advances (exact next step depends
		// on configuration, so we just verify the heading changed).
		await expect(
			page.getByRole('heading', { name: /Where is your Pawrrtal/i })
		).not.toBeVisible({ timeout: 5_000 });
	});
});
