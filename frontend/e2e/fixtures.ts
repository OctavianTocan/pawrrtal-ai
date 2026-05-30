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
 * the response is 2xx, and installs the session cookie into the browser
 * context.
 *
 * `ensureProvisionedWorkspace` adds the workspace seed via the
 * personalization upsert endpoint (which calls
 * `ensure_default_workspace` server-side). Tests that need the
 * sidebar visible call this before navigating.
 *
 * Per the api-setup-not-ui rule, both helpers drive state through
 * the backend, not through UI clicks.
 */

import { type BrowserContext, test as base } from '@playwright/test';
import { E2E_SKIP_ONBOARDING_STORAGE_KEY } from '../features/onboarding/v2/OnboardingFlow';

const BACKEND_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';

const BACKEND_CONFIG_STORAGE_KEY = 'pawrrtal:backend-config';
const SESSION_COOKIE_NAME = 'session_token';

async function readResponseSummary(response: Response): Promise<string> {
	const body = await response.text();
	return body.length > 0 ? `${response.status} ${body}` : `${response.status}`;
}

function extractSessionCookie(setCookie: string | null): string {
	const cookieValue = setCookie?.match(/session_token=([^;]+)/)?.[1];
	if (cookieValue === undefined) {
		throw new Error('Dev login returned 2xx but no session_token cookie.');
	}
	return cookieValue;
}

async function authedBackendFetch({
	cookieValue,
	method,
	path,
	body,
}: {
	cookieValue: string;
	method: 'POST' | 'PUT';
	path: string;
	body: Record<string, unknown>;
}): Promise<Response> {
	return fetch(`${BACKEND_URL}${path}`, {
		method,
		headers: {
			'content-type': 'application/json',
			cookie: `${SESSION_COOKIE_NAME}=${cookieValue}`,
			'x-e2e-run': '1',
		},
		body: JSON.stringify(body),
	});
}

/**
 * Authenticate the supplied browser context with the dev-admin user.
 *
 * Hits the backend `/auth/dev-login` endpoint directly. The Set-Cookie
 * header is captured into the context's cookie jar so subsequent
 * `page.goto()` calls share the auth session.
 */
async function devLogin(context: BrowserContext): Promise<string> {
	const response = await fetch(`${BACKEND_URL}/auth/dev-login`, {
		method: 'POST',
		headers: { 'x-e2e-run': '1' },
	});
	if (!response.ok) {
		throw new Error(
			`Dev login failed (${await readResponseSummary(response)}). Make sure ADMIN_EMAIL + ADMIN_PASSWORD are set in backend/.env and the backend is running.`
		);
	}
	const cookieValue = extractSessionCookie(response.headers.get('set-cookie'));
	const backendHost = new URL(BACKEND_URL).hostname;
	const cookieUrls = Array.from(
		new Set([`http://${backendHost}`, 'http://localhost', 'http://127.0.0.1'])
	);
	await context.addCookies(
		cookieUrls.map((url) => ({
			name: SESSION_COOKIE_NAME,
			value: cookieValue,
			url,
			httpOnly: true,
			secure: false,
			sameSite: 'Lax' as const,
		}))
	);
	return cookieValue;
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
async function ensureProvisionedWorkspace(cookieValue: string): Promise<void> {
	const response = await authedBackendFetch({
		cookieValue,
		method: 'PUT',
		path: '/api/v1/personalization',
		body: { name: 'E2E Admin' },
	});
	if (!response.ok) {
		throw new Error(
			`Provisioning the dev workspace failed (${await readResponseSummary(response)}). The PUT /api/v1/personalization endpoint is required for sidebar / home-shell tests to land on a populated app shell.`
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
async function seedConversation(cookieValue: string): Promise<void> {
	const conversationId = crypto.randomUUID();
	const response = await authedBackendFetch({
		cookieValue,
		method: 'POST',
		path: `/api/v1/conversations/${conversationId}`,
		body: { title: 'E2E Seed Conversation' },
	});
	if (!response.ok) {
		throw new Error(
			`Seeding the dev conversation failed (${await readResponseSummary(response)}). The sidebar Projects header only renders when at least one chat row exists.`
		);
	}
}

interface E2EFixtures {
	authenticatedPage: void;
	authenticatedPageWithWorkspace: void;
	authenticatedPageWithWorkspaceAndChat: void;
	/**
	 * When false, the onboarding skip flag is NOT injected so the wizard
	 * opens normally. Defaults to true for all specs except onboarding.
	 */
	skipOnboarding: boolean;
}

export const test = base.extend<E2EFixtures>({
	skipOnboarding: [true, { option: true }],

	context: async ({ context, skipOnboarding }, use) => {
		await context.addInitScript(
			({
				skipKey,
				configKey,
				backendUrl,
				shouldSkip,
			}: {
				skipKey: string;
				configKey: string;
				backendUrl: string;
				shouldSkip: boolean;
			}) => {
				try {
					if (shouldSkip) {
						window.localStorage.setItem(skipKey, '1');
						if (!window.localStorage.getItem(configKey)) {
							window.localStorage.setItem(
								configKey,
								JSON.stringify({ url: backendUrl, apiKey: '' })
							);
						}
					}
				} catch {
					// localStorage may throw in private browsing
				}
			},
			{
				skipKey: E2E_SKIP_ONBOARDING_STORAGE_KEY,
				configKey: BACKEND_CONFIG_STORAGE_KEY,
				backendUrl: BACKEND_URL,
				shouldSkip: skipOnboarding,
			}
		);
		await use(context);
	},

	authenticatedPage: [
		async ({ context }, use) => {
			await devLogin(context);
			await use();
		},
		{ auto: false },
	],

	authenticatedPageWithWorkspace: [
		async ({ context }, use) => {
			const cookieValue = await devLogin(context);
			await ensureProvisionedWorkspace(cookieValue);
			await use();
		},
		{ auto: false },
	],

	authenticatedPageWithWorkspaceAndChat: [
		async ({ context }, use) => {
			const cookieValue = await devLogin(context);
			await ensureProvisionedWorkspace(cookieValue);
			await seedConversation(cookieValue);
			await use();
		},
		{ auto: false },
	],
});

export const expect = test.expect;
