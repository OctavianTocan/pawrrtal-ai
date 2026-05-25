/**
 * Sidebar smoke: open, close, and project header visibility.
 *
 * The sidebar's Projects section is only rendered when the chat list
 * is non-empty (see ``NavChatsView`` for the gate). Tests seed the
 * required state via the same ``context.request`` so cookies from
 * dev-login carry into every subsequent setup call.
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

	test('renders the Projects header + create-project button', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByText('Projects')).toBeVisible();
		await expect(page.getByRole('button', { name: 'Create new project' })).toBeVisible();
	});

	test('opens the Create project modal with a name input', async ({ page }) => {
		await page.goto('/');
		await page.getByRole('button', { name: 'Create new project' }).click();
		await expect(page.getByRole('heading', { name: 'Create project' })).toBeVisible();
		await expect(page.getByLabel('Project name')).toBeVisible();
		await expect(page.getByRole('button', { name: 'Create project' })).toBeDisabled();
	});
});
