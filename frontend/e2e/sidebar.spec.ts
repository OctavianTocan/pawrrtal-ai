/**
 * Sidebar smoke: open, close, and project header visibility.
 *
 * The sidebar's Projects section is only rendered when the chat list
 * is non-empty (see ``NavChatsView`` for the gate). We use the
 * ``authenticatedPageWithWorkspaceAndChat`` fixture so the test
 * starts on a fully populated sidebar.
 *
 * Multi-select + drag-and-drop need a richer fixture (a real
 * conversation list seeded via the backend) — split into a follow-up
 * suite once the seed helper lands.
 */

import { expect, test } from './fixtures';

test.describe('sidebar', () => {
	test.beforeEach(async ({ context, request }) => {
		// Re-use the shared fixture's setup so the test is otherwise
		// independent of the suite ordering.
		await context.request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/auth/dev-login`
		);
		await request.put(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/api/v1/personalization`,
			{
				data: { name: 'E2E Admin' },
			}
		);
		await request.post(
			`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/api/v1/conversations/${crypto.randomUUID()}`,
			{ data: { title: 'E2E Seed Conversation' } }
		);
	});

	test('renders the Projects header + create-project button', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByRole('button', { name: /Projects/i }).first()).toBeVisible();
		await expect(page.getByRole('button', { name: 'Create new project' })).toBeAttached();
	});

	test('opens the Create project modal with a name input', async ({ page }) => {
		await page.goto('/');
		await page.getByRole('button', { name: 'Create new project' }).click();
		await expect(page.getByRole('heading', { name: 'Create project' })).toBeVisible();
		await expect(page.getByLabel('Project name')).toBeVisible();
		await expect(page.getByRole('button', { name: 'Create project' })).toBeDisabled();
	});
});
