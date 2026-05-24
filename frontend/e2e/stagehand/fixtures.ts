/**
 * Stagehand fixtures for the AI-driven E2E suite.
 *
 * Provides:
 *
 *   1. `stagehand` — a `Stagehand` instance running in `env: "LOCAL"`
 *      mode (no Browserbase account needed — the LLM call goes to
 *      OpenAI / Anthropic / Google directly via standard `*_API_KEY`
 *      env vars). Configured with:
 *        - shared on-disk action cache (`.stagehand-cache/`) so repeat
 *          runs skip the LLM and hit cached selectors immediately
 *          (per Stagehand caching docs).
 *        - locked viewport (1280×720) so the accessibility-tree hash
 *          stays stable across runs — keeps cache hit-rate high.
 *        - dev-admin session cookie pre-loaded via `POST /auth/dev-login`
 *          on the FastAPI backend, injected into the BrowserContext
 *          BEFORE the spec navigates. Per the project's
 *          API-setup-not-UI rule.
 *        - `pawrrtal:e2e-skip-onboarding` localStorage flag injected
 *          via `addInitScript` so the v2 OnboardingFlow never auto-opens
 *          on `/`. The flag is honored inside `OnboardingFlow.tsx` and
 *          gates both the initial open and the workspace-selector open
 *          event so a stray click can't re-open it mid-spec. See
 *          `frontend/features/onboarding/v2/OnboardingFlow.tsx` for
 *          the gate implementation.
 *
 *   2. `navigateToApp(path)` — helper that opens an absolute frontend
 *      URL and waits for `domcontentloaded` (NOT `networkidle` — the
 *      chat surface holds a long-lived SSE connection so the network is
 *      never idle).
 *
 *   3. Skip-with-actionable-message when no LLM env var is set, so
 *      `bun run e2e:stagehand` doesn't fail in a confusing way.
 *
 * Each spec destructures `({ stagehand, navigateToApp })` and calls
 * `stagehand.act(...)`, `stagehand.extract(...)`, etc.
 */

import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { Stagehand } from '@browserbasehq/stagehand';
import { test as base } from '@playwright/test';
import { E2E_SKIP_ONBOARDING_STORAGE_KEY } from '../../features/onboarding/v2/OnboardingFlow';

const BACKEND_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';
const FRONTEND_URL = process.env.E2E_BASE_URL ?? 'http://localhost:53001';

/**
 * Repo-relative cache directory shared across all Stagehand specs.
 *
 * Stagehand persists cached action selectors here on first run so
 * subsequent runs skip the LLM entirely (per the official caching
 * guide). Committed to git so CI gets the warm cache too.
 */
const STAGEHAND_CACHE_DIR = path.resolve(__dirname, '../../.stagehand-cache');

/**
 * Locked viewport for cache-hit stability.
 *
 * Per Stagehand caching docs: small differences in viewport produce
 * different accessibility trees and therefore different cache keys.
 * Pin a single size for the whole suite so the cache is reusable.
 */
const VIEWPORT = { width: 1280, height: 720 } as const;

/**
 * GIF playback is set to 2 fps (0.5s per frame) so each Stagehand
 * action lingers long enough to be visually parseable in PR descriptions
 * and Slack previews. Faster framerates blur consecutive screenshots
 * together and slower ones make the playback feel laggy. Tuned by hand.
 */
const GIF_FRAMERATE = '2';
/** Output GIF width in pixels — height auto-scales to maintain aspect ratio. */
const GIF_WIDTH_PX = '720';
/**
 * Interval at which the fixture captures a screenshot of the active
 * Stagehand page during the test. 500ms matches the GIF playback rate
 * (2fps), so wall-clock time → GIF time stays 1:1. Increase if specs
 * are short and the GIF feels jittery; decrease for very long specs
 * if you want a shorter GIF.
 */
const GIF_FRAME_INTERVAL_MS = 500;

/**
 * Pick the LLM model string Stagehand should use.
 *
 * Stagehand expects `provider/model-id` strings. Order: Google → OpenAI
 * → Anthropic.
 *
 * Default Google model is `gemini-3-flash-preview` (NOT Pro Preview).
 * Tier 1 capped Pro Preview at 250 requests/day, which a single full
 * suite run blew past in minutes. Flash Preview is ~10,000 RPD on the
 * same tier, ~2-3× faster, and much cheaper per call — and it's still
 * very capable at observe/extract for this suite. Override at the
 * command line via `GOOGLE_MODEL=gemini-3.1-pro-preview` if you've
 * upgraded billing or want the bigger model for a specific run.
 */
function _selectModel(): string | null {
	if (process.env.STAGEHAND_GOOGLE_API_KEY) {
		return `google/${process.env.GOOGLE_MODEL ?? 'gemini-3-flash-preview'}`;
	}
	if (process.env.STAGEHAND_OPENAI_API_KEY) {
		return `openai/${process.env.OPENAI_MODEL ?? 'gpt-5.4'}`;
	}
	if (process.env.STAGEHAND_ANTHROPIC_API_KEY) return 'anthropic/claude-haiku-4-5';
	return null;
}

/**
 * Hit the backend dev-login endpoint and return the session cookie
 * value so we can inject it into a fresh Stagehand context.
 *
 * FastAPI-Users' cookie transport returns 204 No Content on success
 * (cookie IS the payload), so we accept any 2xx and read the cookie
 * off the response.
 */
async function _devLoginCookie(): Promise<string> {
	const response = await fetch(`${BACKEND_URL}/auth/dev-login`, { method: 'POST' });
	if (!(response.status >= 200 && response.status < 300)) {
		throw new Error(
			`Dev login failed (${response.status}). Make sure ADMIN_EMAIL + ADMIN_PASSWORD are set in backend/.env and the backend is running at ${BACKEND_URL}.`
		);
	}
	const setCookie = response.headers.get('set-cookie') ?? '';
	const match = setCookie.match(/session_token=([^;]+)/);
	const cookieValue = match?.[1];
	if (cookieValue === undefined) {
		throw new Error(
			`Dev login returned 2xx but no session_token cookie in Set-Cookie. Has the auth backend been changed to a non-cookie transport?`
		);
	}
	return cookieValue;
}

interface StagehandFixtures {
	/** Live Stagehand instance with the dev-admin cookie pre-loaded. */
	stagehand: Stagehand;
	/**
	 * Navigate the active Stagehand page to a frontend route and wait
	 * for the DOM to be ready. Pass an app-relative path (`/settings`);
	 * the helper joins it with `E2E_BASE_URL`.
	 *
	 * Onboarding is auto-skipped via the `pawrrtal:e2e-skip-onboarding`
	 * localStorage flag set in the Stagehand init script — every spec
	 * lands signed-in with no modal in the way.
	 */
	navigateToApp: (appPath: string) => Promise<void>;
}

export const test = base.extend<StagehandFixtures>({
	stagehand: async ({ browser: _browser }, use, testInfo) => {
		const model = _selectModel();
		if (model === null) {
			test.skip(
				true,
				'Stagehand E2E tests need an LLM. Set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY.'
			);
			return;
		}

		mkdirSync(STAGEHAND_CACHE_DIR, { recursive: true });

		const cookieValue = await _devLoginCookie();
		mkdirSync(testInfo.outputDir, { recursive: true });

		const stagehand = new Stagehand({
			env: 'LOCAL',
			verbose: 2,
			model,
			cacheDir: STAGEHAND_CACHE_DIR,
			localBrowserLaunchOptions: {
				headless: process.env.STAGEHAND_HEADLESS === '1',
				viewport: { ...VIEWPORT },
			},
		});
		await stagehand.init();

		// Start a periodic-screenshot capture loop on Stagehand's active
		// page. Stagehand's V3Context (a custom CDP wrapper) does NOT
		// expose Playwright's `tracing.start/stop` API — see the type
		// def at `node_modules/@browserbasehq/stagehand/dist/esm/lib/v3/
		// understudy/context.d.ts`. So we can't use Playwright's trace
		// for GIF source frames. Instead we hold a setInterval that
		// dumps a PNG every `GIF_FRAME_INTERVAL_MS` into the test
		// outputDir; the GIF generator stitches them after the test.
		// This loses some fidelity vs trace (no snapshot tree) but
		// gives a real timeline of the agent's actions, which is what
		// PR / Slack reviewers actually want.
		const framesDir = path.join(testInfo.outputDir, '.frames');
		mkdirSync(framesDir, { recursive: true });
		let frameIndex = 0;
		const captureFrame = async (): Promise<void> => {
			try {
				const activePage = stagehand.context.activePage();
				if (activePage === undefined) return;
				const padded = String(frameIndex++).padStart(4, '0');
				await activePage.screenshot({
					path: path.join(framesDir, `frame-${padded}.png`),
					type: 'png',
					fullPage: false,
				});
			} catch {
				// Page may be transitioning between navigations; the next
				// tick will succeed. Swallowing keeps the loop alive.
			}
		};
		const captureTimer = setInterval(() => void captureFrame(), GIF_FRAME_INTERVAL_MS);
		// Best-effort: capture an immediate first frame so the GIF has a
		// baseline shot even on tests that finish in <1s.
		await captureFrame();

		// Inject the dev-admin session cookie BEFORE the spec navigates,
		// so the very first page.goto() lands signed in. Cookie name +
		// shape mirrors what FastAPI-Users' Set-Cookie header would have
		// landed if the spec had logged in via the UI.
		await stagehand.context.addCookies([
			{
				name: 'session_token',
				value: cookieValue,
				domain: 'localhost',
				path: '/',
				httpOnly: true,
				secure: false,
				sameSite: 'Lax',
			},
		]);

		// Suppress the v2 OnboardingFlow modal via the production-side
		// `E2E_SKIP_ONBOARDING_STORAGE_KEY` flag. `addInitScript` runs
		// on every new document BEFORE any page script, so the flag is
		// already set by the time React hydrates and `OnboardingFlow`
		// reads it inside its `useState` lazy initializer. Result: the
		// dialog hydrates closed and never flashes onto the page.
		await stagehand.context.addInitScript(
			({ key }: { key: string }) => {
				try {
					window.localStorage.setItem(key, '1');
				} catch {
					// localStorage can throw in private browsing — the
					// query-param fallback inside OnboardingFlow.tsx
					// covers that case for tests that need it.
				}
			},
			{ key: E2E_SKIP_ONBOARDING_STORAGE_KEY }
		);

		try {
			await use(stagehand);
		} finally {
			// Order: stop the screenshot timer first, take one final
			// frame (so the post-action steady state is visible), then
			// close Stagehand and stitch the GIF.
			clearInterval(captureTimer);
			try {
				await captureFrame();
			} catch {
				/* page already torn down — ignore */
			}
			await stagehand.close();
			await _writeFramesGif(testInfo);
		}
	},

	navigateToApp: async ({ stagehand }, use) => {
		const helper = async (appPath: string): Promise<void> => {
			const page = stagehand.context.pages()[0];
			if (page === undefined) {
				throw new Error('Stagehand context has no initial page; init likely failed.');
			}
			await page.goto(`${FRONTEND_URL}${appPath}`);
			// Wait for DOMContentLoaded — NOT networkidle. The chat
			// surface holds a long-lived SSE connection to
			// `/api/v1/chat`, so the network is never idle. Per the
			// project's no-networkidle rule, we wait for a specific
			// signal: DOM ready means React has hydrated and the
			// accessibility tree is queryable.
			await page.waitForLoadState('domcontentloaded');
		};
		await use(helper);
	},
});

export const expect = test.expect;

/**
 * Build a `run.gif` from the Playwright trace's per-step screenshots,
 * called from the `stagehand` fixture's `finally` block AFTER
 * `stagehand.close()` so trace.zip is guaranteed to be on disk.
 *
 * Pasteable into PR descriptions, GitHub issues, and Slack without
 * needing anyone to download a file.
 *
 * Why trace screenshots and not a webm? Playwright's video config
 * doesn't apply when Stagehand owns the BrowserContext (and Stagehand's
 * own `recordVideo` option isn't reliably plumbed through in v3.3 LOCAL
 * mode). The trace, however, IS reliably captured because it's a
 * Playwright-side facility — and trace.zip contains a sequence of
 * per-step JPEG snapshots (`resources/<hash>.jpeg`) that make a more
 * useful GIF anyway: one frame per logical Stagehand action rather than
 * 30 fps of nothing-changing video.
 *
 * Why a fixture-level helper instead of `test.afterEach`: Playwright's
 * trace flush happens when the BrowserContext closes. Stagehand owns
 * the context, and `stagehand.close()` is called in the fixture
 * teardown — which runs AFTER `test.afterEach`. Running the GIF gen
 * inside `afterEach` therefore sees no trace.zip and silently skips.
 *
 * Logging:
 *   - Success: `[gif] wrote <N>KiB <path>` so the dev running
 *     `just stagehand-e2e` can confirm the artifact exists without
 *     digging through the HTML report.
 *   - Failure: a single-line warning instead of silently swallowing.
 */
async function _writeFramesGif(testInfo: import('@playwright/test').TestInfo): Promise<void> {
	const framesDir = path.join(testInfo.outputDir, '.frames');
	const gifPath = path.join(testInfo.outputDir, 'run.gif');

	if (!existsSync(framesDir)) {
		console.warn(`[gif] no frames dir at ${framesDir} — skipping`);
		return;
	}

	try {
		// Frame names are zero-padded (`frame-0000.png` → `frame-9999.png`),
		// so a plain alphabetical sort is the chronological order.
		const frames = readdirSync(framesDir)
			.filter((name) => name.endsWith('.png'))
			.sort();
		if (frames.length === 0) {
			console.warn(`[gif] no PNG frames captured — skipping`);
			return;
		}

		execFileSync(
			'ffmpeg',
			[
				'-y',
				'-framerate',
				GIF_FRAMERATE,
				'-i',
				path.join(framesDir, 'frame-%04d.png'),
				'-vf',
				`scale=${GIF_WIDTH_PX}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse`,
				'-loop',
				'0',
				gifPath,
			],
			{ stdio: 'ignore' }
		);

		await testInfo.attach('run.gif', { path: gifPath, contentType: 'image/gif' });
		const sizeKiB = Math.round(statSync(gifPath).size / 1024);
		console.log(`[gif] wrote ${sizeKiB}KiB → ${gifPath} (${frames.length} frames)`);
	} catch (error) {
		const reason = error instanceof Error ? error.message : String(error);
		console.warn(`[gif] generation failed: ${reason}`);
	}
}
