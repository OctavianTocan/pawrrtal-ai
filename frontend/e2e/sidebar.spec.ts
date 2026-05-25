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
	test.beforeEach(async ({ context }) => {
		const backend = process.env.E2E_API_URL ?? 'http://localhost:8000';
		// ``context.request`` shares cookies with the browser context, so
		// the dev-login session cookie is available for the personalization
		// and conversation seed calls below.
		const loginResponse = await context.request.post(`${backend}/auth/dev-login`);
		expect(loginResponse.ok()).toBe(true);
		const provisionResponse = await context.request.put(`${backend}/api/v1/personalization`, {
			data: { name: 'E2E Admin' },
		});
		expect(provisionResponse.ok()).toBe(true);
		const conversationResponse = await context.request.post(
			`${backend}/api/v1/conversations/${crypto.randomUUID()}`,
			{ data: { title: 'E2E Seed Conversation' } }
		);
		expect(conversationResponse.ok()).toBe(true);
	});

	test('renders the New chat button and seeded conversation in the sidebar', async ({ page }) => {
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
		// The "New chat" button is always visible in the sidebar header.
		await expect(page.getByRole('button', { name: /New chat/i })).toBeVisible();
		// The seeded conversation appears in the conversation list.
		await expect(page.getByText('E2E Seed Conversation')).toBeVisible({ timeout: 15_000 });
	});

	test('renders the user profile section in the sidebar footer', async ({ page }) => {
		await page.goto('/');
		// The sidebar footer shows the provisioned user name once the
		// personalization query resolves. Allow extra time for cold CI.
		await expect(page.getByText('E2E Admin')).toBeVisible({ timeout: 15_000 });
	});
});
