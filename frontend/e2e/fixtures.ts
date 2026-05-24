/**
 * Shared Playwright fixtures.
 *
 * Every browser context created by this fixture file gets two
 * localStorage entries injected via `addInitScript` (runs before any
 * page script on every new document):
 *
 *   1. `pawrrtal:e2e-skip-onboarding` — suppresses the v2 onboarding
 *      wizard so specs land directly on the chat shell. Tests that
 *      exercise onboarding itself opt out via `skipOnboarding: false`.
 *
 *   2. `pawrrtal:backend-config` — provides a stored backend URL so
 *      `hasBackendConfig()` returns true. Without it `AppShell`
 *      dispatches `OPEN_ONBOARDING_SERVER_STEP_EVENT` on mount, forcing
 *      the wizard to the "Where is your Pawrrtal?" step even when the
 *      skip flag is absent.
 *
 * `authenticatedPage` runs the dev-admin login via the backend (no UI
 * clicks) and forwards the resulting session cookie into the browser
 * context, so every spec starts already signed in. Per the project's
 * api-setup-not-ui rule.
 */

import { type BrowserContext, test as base } from '@playwright/test';
import { E2E_SKIP_ONBOARDING_STORAGE_KEY } from '../features/onboarding/v2/OnboardingFlow';

const BACKEND_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';

const BACKEND_CONFIG_STORAGE_KEY = 'pawrrtal:backend-config';

/**
 * Authenticate the supplied browser context with the dev-admin user.
 *
 * Hits the backend `/auth/dev-login` endpoint directly — the response
 * body is the session payload, and the Set-Cookie header is what the
 * regular browser flow would normally land. We replay that cookie into
 * the context's cookie jar so the next page navigation is signed in.
 */
async function devLogin(context: BrowserContext): Promise<void> {
	const response = await context.request.post(`${BACKEND_URL}/auth/dev-login`);
	if (!response.ok()) {
		throw new Error(
			`Dev login failed (${response.status()}). Make sure ADMIN_EMAIL + ADMIN_PASSWORD are set in backend/.env and the backend is running.`
		);
	}
}

interface E2EFixtures {
	authenticatedPage: void;
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
});

export const expect = test.expect;
