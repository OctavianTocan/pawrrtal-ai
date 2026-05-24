/**
 * Playwright config for the pawrrtal E2E suite.
 *
 * Tests live in `frontend/e2e/`. The suite assumes both servers are
 * already running on the documented dev ports (Next on :3001, FastAPI
 * on :8000) — start them with `just dev` in another terminal before
 * running `just e2e` so we don't fight the dev workflow with
 * `webServer` lifecycles.
 *
 * Per the project rules:
 * - role-based selectors only (no CSS/id locators)
 * - web-first assertions
 * - never wait for `networkidle`
 * - API-driven setup via the backend dev-login endpoint, no UI clicks
 */

import { defineConfig } from '@playwright/test';

const FRONTEND_URL = process.env.E2E_BASE_URL ?? 'http://localhost:53001';
const BACKEND_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';

export default defineConfig({
	testDir: './e2e',
	timeout: 30_000,
	expect: { timeout: 5_000 },
	fullyParallel: false,
	forbidOnly: Boolean(process.env.CI),
	retries: process.env.CI ? 2 : 0,
	workers: 1,
	reporter: [['list']],
	use: {
		baseURL: FRONTEND_URL,
		trace: 'on-first-retry',
		screenshot: 'only-on-failure',
		video: 'retain-on-failure',
		actionTimeout: 10_000,
		extraHTTPHeaders: {
			'x-e2e-run': '1',
		},
	},
	projects: [
		{
			name: 'chromium',
			use: { browserName: 'chromium' },
		},
	],
	metadata: {
		backend: BACKEND_URL,
	},
});
