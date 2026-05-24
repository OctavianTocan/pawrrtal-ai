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
import { expect, test } from './fixtures';

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

test.describe('a11y smoke', () => {
	test('login page has no auto-detectable a11y violations', async ({ page }) => {
		await page.goto('/login');
		const results = await new AxeBuilder({ page: page as never }).withTags(WCAG_TAGS).analyze();
		expect(results.violations).toEqual([]);
	});

	test('authenticated home shell has no auto-detectable a11y violations', async ({
		page,
		context,
	}) => {
		const response = await context.request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/auth/dev-login`
		);
		expect(response.ok()).toBe(true);
		await page.goto('/');
		await expect(page.getByRole('button', { name: /New Session/i })).toBeVisible();
		const results = await new AxeBuilder({ page: page as never }).withTags(WCAG_TAGS).analyze();
		expect(results.violations).toEqual([]);
	});

	test('settings page has no auto-detectable a11y violations', async ({ page, context }) => {
		const response = await context.request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/auth/dev-login`
		);
		expect(response.ok()).toBe(true);
		await page.goto('/settings');
		await expect(page.getByRole('heading', { name: 'General' })).toBeVisible();
		const results = await new AxeBuilder({ page: page as never }).withTags(WCAG_TAGS).analyze();
		expect(results.violations).toEqual([]);
	});

	test('chat composer with a draft has no auto-detectable a11y violations', async ({
		page,
		context,
	}) => {
		const response = await context.request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/auth/dev-login`
		);
		expect(response.ok()).toBe(true);
		await page.goto('/');
		await expect(page.getByRole('button', { name: /New Session/i })).toBeVisible();
		const composer = page.locator('textarea').first();
		await composer.fill('Hello — this is an a11y smoke draft.');
		const results = await new AxeBuilder({ page: page as never }).withTags(WCAG_TAGS).analyze();
		expect(results.violations).toEqual([]);
	});
});
