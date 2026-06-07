/**
 * Onboarding wizard smoke: verify the normal four-step onboarding flow. CI
 * reuses one dev-admin account across specs, so these tests open the flow
 * through its browser event instead of depending on global workspace state from
 * earlier specs.
 */

import type { Page } from '@playwright/test';
import { OPEN_ONBOARDING_FLOW_EVENT } from '../features/onboarding/v2/OnboardingFlow';
import { expect, test } from './fixtures';

test.use({ skipOnboarding: false });

async function openOnboardingFlow(page: Page): Promise<void> {
	const identityHeading = page.getByRole('heading', { name: /Let's get to know you/i });

	await expect
		.poll(
			async () => {
				await page.evaluate((eventName) => {
					window.dispatchEvent(new Event(eventName));
				}, OPEN_ONBOARDING_FLOW_EVENT);
				return identityHeading.isVisible();
			},
			{
				intervals: [100, 250, 500],
				timeout: 10_000,
			}
		)
		.toBe(true);
}

test.describe('onboarding wizard', () => {
	test.beforeEach(async ({ context }) => {
		const response = await context.request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/auth/dev-login`
		);
		expect(response.ok()).toBe(true);
	});

	test('renders the identity step on fresh load', async ({ page }) => {
		await page.goto('/');
		await openOnboardingFlow(page);
		await expect(page.getByRole('heading', { name: /Let's get to know you/i })).toBeVisible({
			timeout: 10_000,
		});
		await expect(page.getByLabel(/Your name/i)).toBeVisible();
	});

	test('Continue button progresses to the context step', async ({ page }) => {
		await page.goto('/');
		await openOnboardingFlow(page);
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
