/**
 * Playwright config for the Stagehand-driven AI E2E suite.
 *
 * Lives separately from the deterministic `playwright.config.ts` so the
 * default `bun run e2e` stays fast + cheap and the AI suite is opt-in
 * via `bun run e2e:stagehand` (or `just stagehand-e2e` from the repo
 * root). Same dev-server assumptions: Next on :3001, FastAPI on :8000,
 * already running via `just dev` in another terminal.
 *
 * Stagehand is run in `env: "LOCAL"` mode — the LLM call goes to
 * OpenAI / Anthropic / Google directly via the standard `*_API_KEY`
 * env vars, no Browserbase account required.
 */

import { defineConfig } from '@playwright/test';

const FRONTEND_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const BACKEND_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e/stagehand',
  // AI agents take longer than deterministic Playwright steps. Each
  // `act` / `extract` round-trips to an LLM (typically 2-10s), and a
  // multi-step spec can chain 5-10 of those calls.
  timeout: 180_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  // LLM responses are non-deterministic; one retry catches transient
  // rate-limits and parser hiccups without masking real bugs.
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  // Two reporters: a live `list` for the terminal AND a self-contained
  // HTML report at `playwright-report/index.html`. The HTML report
  // includes per-step screenshots, the full Playwright trace timeline
  // (DOM snapshots, network log, console output), and any captured
  // videos — open it with `bunx playwright show-report` after a run.
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  // Per-test artifacts land here. Wipe before each run so `test-results/`
  // only ever contains the latest run's traces, screenshots, and videos.
  outputDir: 'test-results',
  use: {
    baseURL: FRONTEND_URL,
    // AI specs are non-deterministic and expensive to debug — capture
    // EVERYTHING on every run, not just on failure. The trace alone
    // gives a step-by-step timeline of every Stagehand action with
    // before/after DOM snapshots and the network log.
    trace: 'on',
    screenshot: 'on',
    video: 'on',
    // `act` and `extract` perform their own DOM waits via Stagehand;
    // keep Playwright's actionTimeout generous to avoid double-timeout.
    actionTimeout: 30_000,
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
    suite: 'stagehand',
  },
});
