/**
 * @axe-core/playwright accessibility smoke specs.
 *
 * Closes #276. Catches the high-signal subset of a11y regressions that
 * matters most: missing labels, color contrast, duplicate IDs, ARIA
 * misuse, focusable elements without accessible names.  Automated scans
 * never replace manual a11y testing — they keep us from shipping a
 * regression unnoticed.
 *
 * WCAG scope: 2.0 and 2.1, levels A + AA.  Anything more strict is a
 * judgment call per surface and belongs in a focused spec rather than
 * the smoke suite.
 *
 * If a vendor surface (Stripe iframe, Google OAuth picker, etc.) trips
 * a specific rule we cannot remediate, use `.disableRules(['rule-id'])`
 * with an inline comment naming the surface and the trade-off.
 */

import AxeBuilder from '@axe-core/playwright';
import type { BrowserContext } from '@playwright/test';
import { expect, test } from './fixtures';

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

/**
 * Authenticate + provision a default workspace via the backend so the
 * authenticated home shell / settings page render the same chrome a
 * real user sees. ``context.request`` shares cookies with the browser
 * context, so the dev-login session carries into the personalization
 * upsert that triggers ``ensure_default_workspace`` server-side.
 */
async function seedAuthenticatedHomeShell(context: BrowserContext): Promise<void> {
	const backend = process.env.E2E_API_URL ?? 'http://localhost:8000';
	const loginResponse = await context.request.post(`${backend}/auth/dev-login`);
	expect(loginResponse.ok()).toBe(true);
	const provisionResponse = await context.request.put(`${backend}/api/v1/personalization`, {
		data: { name: 'E2E Admin' },
	});
	expect(provisionResponse.ok()).toBe(true);
}

test.describe('a11y smoke', () => {
	test('login page has no auto-detectable a11y violations', async ({ page }) => {
		await page.goto('/login');
		// AxeBuilder's `Page` type comes from `playwright-core`'s d.ts; our
		// fixture's `page` comes from `@playwright/test`. The two are
		// structurally compatible but TS sees them as distinct nominal
		// types — cast through `as never` to silence the duplicate-module
		// noise without `as any`.
		const results = await new AxeBuilder({ page: page as never }).withTags(WCAG_TAGS).analyze();
		expect(results.violations).toEqual([]);
	});

	test('authenticated home shell has no auto-detectable a11y violations', async ({
		page,
		context,
	}) => {
		await seedAuthenticatedHomeShell(context);
		await page.goto('/');
		await expect(
			page.getByPlaceholder(/^(Ask|Type|Send)/i).or(page.getByRole('textbox'))
		).toBeVisible();
		const results = await new AxeBuilder({ page: page as never }).withTags(WCAG_TAGS).analyze();
		expect(results.violations).toEqual([]);
	});

	test('settings page has no auto-detectable a11y violations', async ({ page, context }) => {
		await seedAuthenticatedHomeShell(context);
		await page.goto('/settings');
		const results = await new AxeBuilder({ page: page as never }).withTags(WCAG_TAGS).analyze();
		expect(results.violations).toEqual([]);
	});

	test('chat composer with a draft has no auto-detectable a11y violations', async ({
		page,
		context,
	}) => {
		await seedAuthenticatedHomeShell(context);
		await page.goto('/');
		const composer = page
			.getByPlaceholder(/^(Ask|Type|Send)/i)
			.or(page.getByRole('textbox'))
			.first();
		await composer.fill('Hello — this is an a11y smoke draft.');
		const results = await new AxeBuilder({ page: page as never }).withTags(WCAG_TAGS).analyze();
		expect(results.violations).toEqual([]);
	});
});
