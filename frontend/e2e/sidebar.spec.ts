/**
 * Sidebar smoke: the authenticated shell renders the sidebar with the
 * key affordances (new session, search, user identity).
 */

import { expect, test } from './fixtures';

test.describe('sidebar', () => {
	test.beforeEach(async ({ context }) => {
		const response = await context.request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/auth/dev-login`
		);
		expect(response.ok()).toBe(true);
	});

	test('renders the New Session button and search', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByRole('button', { name: /New Session/i })).toBeVisible();
		await expect(page.getByPlaceholder(/search/i)).toBeVisible();
	});

	test('renders the workspace selector in the header', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByRole('button', { name: /Pawrrtal/i }).first()).toBeVisible();
	});
});
