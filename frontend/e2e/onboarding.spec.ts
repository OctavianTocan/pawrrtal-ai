/**
 * Onboarding wizard smoke: when the authenticated user has no workspace yet,
 * AppShell opens the normal four-step onboarding flow. We verify the wizard
 * opens at Identity and that Continue advances to Context.
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

	test('renders the identity step on fresh load', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByRole('heading', { name: /Let's get to know you/i })).toBeVisible({
			timeout: 10_000,
		});
		await expect(page.getByLabel(/Your name/i)).toBeVisible();
	});

	test('Continue button progresses to the context step', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByRole('heading', { name: /Let's get to know you/i })).toBeVisible({
			timeout: 10_000,
		});
		await page
			.getByRole('button', { name: /Continue/i })
			.first()
			.click();
		await expect(
			page.getByRole('heading', { name: /Let's give your agent some context about you/i })
		).toBeVisible({ timeout: 5_000 });
	});
});
