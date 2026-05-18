/**
 * Settings page smoke: each nav row navigates without crashing and the
 * key sections render their headings.
 */

import { expect, test } from './fixtures';

test.describe('settings page', () => {
	test.beforeEach(async ({ context, request }) => {
		const loginResponse = await context.request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/auth/dev-login`
		);
		expect(loginResponse.ok()).toBe(true);
		// Settings page sits under the app shell which gates rendering
		// on a provisioned workspace. Trigger personalization upsert to
		// satisfy ``useOnboardingReadiness.hasWorkspaceReady``.
		const provisionResponse = await request.put(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/api/v1/personalization`,
			{ data: { name: 'E2E Admin' } }
		);
		expect(provisionResponse.ok()).toBe(true);
	});

	test('General tab renders Profile / Preferences / Notifications groups', async ({ page }) => {
		await page.goto('/settings');
		await expect(page.getByRole('heading', { name: 'General' })).toBeVisible();
		await expect(page.getByText('Profile', { exact: true })).toBeVisible();
		await expect(page.getByText('Preferences', { exact: true })).toBeVisible();
		await expect(page.getByText('Notifications', { exact: true })).toBeVisible();
	});

	test('Archived chats tab renders an empty state or list', async ({ page }) => {
		await page.goto('/settings');
		await page.getByRole('button', { name: 'Archived chats' }).click();
		await expect(page.getByRole('heading', { name: 'Archived chats' })).toBeVisible();
		// Either the empty state or at least one Unarchive button must be visible.
		const unarchive = page.getByRole('button', { name: 'Unarchive' }).first();
		const empty = page.getByRole('heading', { name: 'No archived chats' });
		await expect(unarchive.or(empty)).toBeVisible();
	});
});
