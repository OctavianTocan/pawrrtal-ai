/**
 * Sidebar smoke: authenticated sidebar renders conversation list and controls.
 *
 * Tests seed a conversation via the backend API so the sidebar has
 * content to render. ``context.request`` shares cookies with the
 * browser context so dev-login auth carries into every setup call.
 *
 * Multi-select + drag-and-drop need a richer fixture (a real
 * conversation list seeded via the backend) — split into a follow-up
 * suite once the seed helper lands.
 */

import { expect, test } from './fixtures';

test.describe('sidebar', () => {
	test('renders the seeded conversation in the sidebar', async ({
		page,
		authenticatedPageWithWorkspaceAndChat,
	}) => {
		void authenticatedPageWithWorkspaceAndChat;
		// Wait for the conversations API response alongside navigation so the
		// sidebar has data before the assertion fires. Without this, a slow
		// SQLite cold-query in CI can race with the assertion timeout.
		const [conversationsResponse] = await Promise.all([
			page.waitForResponse(
				(resp) =>
					resp.url().includes('/api/v1/conversations') &&
					resp.request().method() === 'GET',
				{ timeout: 15_000 }
			),
			page.goto('/'),
		]);
		expect(conversationsResponse.ok()).toBe(true);
		// The seeded conversation appears in the conversation list, and the
		// primary New Session control remains accessible by name.
		await expect(page.getByRole('button', { name: /new session/i })).toBeVisible({
			timeout: 15_000,
		});
		await expect(page.getByText('E2E Seed Conversation').first()).toBeVisible({
			timeout: 15_000,
		});
	});

	test('renders the user profile section in the sidebar footer', async ({
		page,
		authenticatedPageWithWorkspace,
	}) => {
		void authenticatedPageWithWorkspace;
		await page.goto('/');
		// The sidebar footer shows the provisioned user name once the
		// personalization query resolves. Allow extra time for cold CI.
		await expect(page.getByText('E2E Admin')).toBeVisible({ timeout: 15_000 });
	});
});
