#!/usr/bin/env node
/**
 * Dev-mode browser-console smoke check.
 *
 * Drives Vercel's `agent-browser` CLI to navigate the app under
 * `next dev` (Turbopack + React 19 strict) and fails the run if the
 * browser console emits any errors or uncaught exceptions on the
 * cold-boot routes.  Caught the React-19 `<script>` hydration class
 * of regression on `development` once already (PR #134 + #135).
 *
 * Why agent-browser instead of Playwright: the project already uses
 * `agent-browser` for visual-regression on the React Native side,
 * and pulling in a Playwright dependency just for one console check
 * is overhead.  The CLI returns clean JSON via `--json`, the binary
 * is cached on the self-hosted runner, and there's no test-runner
 * scaffolding to maintain.  This file is just a thin orchestrator
 * over the CLI.
 *
 * Usage:
 *   node scripts/dev-console-smoke.mjs
 *
 * Env:
 *   DEV_URL   base URL of the running dev server (default
 *             `http://localhost:3001`).
 *
 * Exit codes:
 *   0 — every cold-boot route is silent
 *   1 — at least one route had a real (non-allowlisted) console
 *       error or page-error; offending entries printed.
 */

import { spawnSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import process from 'node:process';

const DEV_URL = process.env.DEV_URL ?? 'http://localhost:3001';
const AGENT_BROWSER_SOCKET_DIR =
	process.env.AGENT_BROWSER_SOCKET_DIR ?? `/tmp/pawrrtal-agent-browser-${process.pid}`;
mkdirSync(AGENT_BROWSER_SOCKET_DIR, { recursive: true });

/** Routes a cold-boot user hits first. Each is checked independently
 *  so a regression in one doesn't mask regressions in another. */
const COLD_BOOT_ROUTES = ['/login', '/', '/docs', '/docs/handbook', '/docs/product'];

/** How long to keep the page open after navigation before scraping
 *  the console.  React 19 hydration warnings fire on effect schedule,
 *  so a beat past `load` is enough to catch them without making the
 *  smoke slow. */
const POST_LOAD_WAIT_MS = 4_000;

/**
 * Allowlist of console.error / pageerror messages we know are
 * CI-environment artefacts, not real app bugs.  Each entry MUST have
 * a comment naming the cause.  If the underlying cause is fixed,
 * delete the entry rather than letting it decay into a catch-all.
 *
 * Pattern guidance: tie matches to a structural marker (a specific
 * URL host, an exact stable string) rather than a substring that
 * could shadow real React errors.
 */
const ALLOWLIST = [
	// Next.js dev-server HMR WebSocket fails to reconnect cleanly
	// when the smoke tears the page down right after asserting.
	// Real users keep the connection open; the underlying compile
	// itself is fine.
	/WebSocket connection to '.+\/_next\/webpack-hmr/,
	// Bare-string `Event` console.error Chromium emits when a
	// WebSocket fails before any frame.  Pairs with the entry above.
	/^Event$/,
];

function isAllowlisted(text) {
	return ALLOWLIST.some((pattern) => pattern.test(text));
}

function ab(...args) {
	const out = spawnSync('agent-browser', args, {
		encoding: 'utf8',
		env: { ...process.env, AGENT_BROWSER_SOCKET_DIR },
	});
	if (out.status !== 0 && out.status !== null) {
		process.stderr.write(out.stderr ?? '');
		process.stderr.write(out.stdout ?? '');
		throw new Error(`agent-browser ${args.join(' ')} exited ${out.status}`);
	}
	return out.stdout ?? '';
}

function abJson(...args) {
	const raw = ab(...args, '--json');
	if (!raw.trim()) return [];
	try {
		const parsed = JSON.parse(raw);
		return Array.isArray(parsed) ? parsed : [];
	} catch (err) {
		throw new Error(
			`agent-browser ${args.join(' ')} returned non-JSON: ${err.message}\n---\n${raw}`
		);
	}
}

function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

async function checkRoute(route) {
	const url = `${DEV_URL}${route}`;
	console.log(`[dev-console-smoke] navigating to ${url}`);

	// Clear console + errors first so this route's check only sees
	// its own output, not anything from the prior route.
	ab('console', '--clear');
	ab('errors', '--clear');

	ab('open', url);
	await sleep(POST_LOAD_WAIT_MS);

	const consoleMessages = abJson('console');
	const pageErrors = abJson('errors');

	const captured = [];
	for (const msg of consoleMessages) {
		// `agent-browser console --json` returns entries with a
		// `type` field; we only fail on `error` (warn/log/info are
		// noise we deliberately ignore).
		if (msg.type !== 'error') continue;
		const text = msg.text ?? '';
		if (isAllowlisted(text)) continue;
		captured.push({ kind: 'console.error', text });
	}
	for (const err of pageErrors) {
		const text = err.text ?? err.message ?? JSON.stringify(err);
		if (isAllowlisted(text)) continue;
		captured.push({ kind: 'pageerror', text });
	}

	return captured;
}

async function main() {
	const failures = [];
	for (const route of COLD_BOOT_ROUTES) {
		const errs = await checkRoute(route);
		if (errs.length > 0) {
			failures.push({ route, errors: errs });
		} else {
			console.log(`[dev-console-smoke] ${route}: clean`);
		}
	}

	// Always close the agent-browser session so the smoke leaves no
	// orphan Chrome processes on the runner.
	ab('close', '--all');

	if (failures.length === 0) {
		console.log('[dev-console-smoke] OK — every cold-boot route silent');
		return;
	}

	console.error('\n[dev-console-smoke] FAILED — console errors on dev boot:\n');
	for (const f of failures) {
		console.error(`  ${f.route}:`);
		for (const e of f.errors) {
			console.error(`    [${e.kind}] ${e.text.slice(0, 400)}`);
		}
	}
	console.error(
		'\nIf a third-party library is emitting unavoidable dev-only noise, ' +
			'add a narrow regex to ALLOWLIST in this file with a TODO + reason ' +
			'— do NOT widen the matcher.'
	);
	process.exitCode = 1;
}

await main();
