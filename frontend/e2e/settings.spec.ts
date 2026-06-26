/**
 * Settings page smoke: each nav row navigates without crashing and the
 * key sections render their headings.
 */

import { expect, test } from './fixtures';

test.describe('settings page', () => {
  test.beforeEach(async ({ context }) => {
    const backend = process.env.E2E_API_URL ?? 'http://localhost:8000';
    // ``context.request`` shares cookies with the browser context, so
    // the dev-login session carries into the personalization upsert.
    const loginResponse = await context.request.post(`${backend}/auth/dev-login`);
    expect(loginResponse.ok()).toBe(true);
    // Settings page sits under the app shell which gates rendering
    // on a provisioned workspace. Trigger personalization upsert to
    // satisfy ``useOnboardingReadiness.hasWorkspaceReady``.
    const provisionResponse = await context.request.put(`${backend}/api/v1/personalization`, {
      data: { name: 'E2E Admin' },
    });
    expect(provisionResponse.ok()).toBe(true);
  });

  test('General tab renders Profile and Notifications groups', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'General' })).toBeVisible();
    await expect(page.getByText('Profile', { exact: true })).toBeVisible();
    // "Preferences" card was removed — it duplicated the Appearance
    // rail item. See GeneralSection.tsx for the rationale.
    await expect(page.getByText('Notifications', { exact: true })).toBeVisible();
  });

  test('Archived chats tab renders without crashing', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: 'Archived chats' }).click();
    // Multiple elements expose the "Archived chats" name (the sidebar tab,
    // the section heading, the mobile breadcrumb). The description below is
    // unique to the panel and a stronger signal that it actually rendered.
    await expect(page.getByText(/Conversations you've archived/i)).toBeVisible();
  });
});
