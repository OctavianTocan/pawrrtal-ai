/**
 * Shared Playwright fixtures.
 *
 * The suite needs two distinct authenticated states — onboarding tests
 * exercise the personalization wizard (which only opens when the user
 * has no workspace yet), while home-shell / sidebar tests expect a
 * fully provisioned workspace. Splitting the state setup into two
 * fixtures keeps each test self-contained and prevents cross-test
 * state leakage.
 *
 * `devLogin` does just the auth half: hits `/auth/dev-login`, confirms
 * the response is 2xx, and returns. The session cookie lands in the
 * context's cookie jar automatically.
 *
 * `ensureProvisionedWorkspace` adds the workspace seed via the
 * personalization upsert endpoint (which calls
 * `ensure_default_workspace` server-side). Tests that need the
 * sidebar visible call this before navigating.
 *
 * Per the api-setup-not-ui rule, both helpers drive state through
 * the backend, not through UI clicks.
 */

import { type APIRequestContext, type BrowserContext, test as base } from '@playwright/test';

const BACKEND_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';

/**
 * Authenticate the supplied browser context with the dev-admin user.
 *
 * Hits the backend `/auth/dev-login` endpoint directly. The Set-Cookie
 * header is captured into the context's cookie jar so subsequent
 * `page.goto()` calls share the auth session.
 */
async function devLogin(context: BrowserContext): Promise<void> {
	const response = await context.request.post(`${BACKEND_URL}/auth/dev-login`);
	if (!response.ok()) {
		throw new Error(
			`Dev login failed (${response.status()}). Make sure ADMIN_EMAIL + ADMIN_PASSWORD are set in backend/.env and the backend is running.`
		);
	}
}

/**
 * Provision a default workspace for the authenticated user.
 *
 * Posts a minimal personalization profile, which triggers
 * `ensure_default_workspace` server-side. Idempotent — calling it
 * twice in the same test is safe. Tests that need the home shell
 * fully rendered (sidebar, chat composer, settings) call this after
 * `devLogin`.
 */
async function ensureProvisionedWorkspace(request: APIRequestContext): Promise<void> {
	const response = await request.put(`${BACKEND_URL}/api/v1/personalization`, {
		data: {
			name: 'E2E Admin',
		},
	});
	if (!response.ok()) {
		throw new Error(
			`Provisioning the dev workspace failed (${response.status()}). The PUT /api/v1/personalization endpoint is required for sidebar / home-shell tests to land on a populated app shell.`
		);
	}
}

/**
 * Seed one conversation so the sidebar renders the Projects section.
 *
 * ``NavChatsView`` hides the Projects header while the chat list is
 * empty (see the inline comment near the ``<ProjectsList />`` mount).
 * Tests that assert on Projects-related UI need at least one
 * conversation to exist. We generate a UUID client-side and POST it
 * to ``/api/v1/conversations/{id}`` — matching the FE's
 * ``createConversationFirst`` pattern.
 */
async function seedConversation(request: APIRequestContext): Promise<void> {
	const conversationId = crypto.randomUUID();
	const response = await request.post(`${BACKEND_URL}/api/v1/conversations/${conversationId}`, {
		data: { title: 'E2E Seed Conversation' },
	});
	if (!response.ok()) {
		throw new Error(
			`Seeding the dev conversation failed (${response.status()}). The sidebar Projects header only renders when at least one chat row exists.`
		);
	}
}

export const test = base.extend<{
	authenticatedPage: void;
	authenticatedPageWithWorkspace: void;
	authenticatedPageWithWorkspaceAndChat: void;
}>({
	authenticatedPage: [
		async ({ context }, use) => {
			await devLogin(context);
			await use();
		},
		{ auto: false },
	],

	authenticatedPageWithWorkspace: [
		async ({ context }, use) => {
			await devLogin(context);
			await ensureProvisionedWorkspace(context.request);
			await use();
		},
		{ auto: false },
	],

	authenticatedPageWithWorkspaceAndChat: [
		async ({ context }, use) => {
			await devLogin(context);
			await ensureProvisionedWorkspace(context.request);
			await seedConversation(context.request);
			await use();
		},
		{ auto: false },
	],
});

export const expect = test.expect;
