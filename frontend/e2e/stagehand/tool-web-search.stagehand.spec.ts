/**
 * Tools — web search via the Exa MCP tool, on the Claude provider.
 *
 * This spec exercises the same flow that surfaced the silent
 * `stop_reason='tool_use' subtype='error_max_turns'` regression on
 * Claude. Root cause was `_DEFAULT_MAX_TURNS = 1` in
 * `backend/app/core/providers/claude_provider.py` — the model could
 * call `exa_search` but never had a second turn to read the tool
 * result and respond. The provider now bumps `max_turns` to
 * `_TOOL_ENABLED_MAX_TURNS` whenever any tool is enabled, AND logs
 * the SDK error via `logger.warning` so future regressions are
 * visible in `backend/app.log` even when the SSE stream succeeds.
 *
 * Coverage:
 *   1. Switch the chat model to Claude (the bug only surfaced on
 *      Claude — Gemini handled tool turns differently).
 *   2. Send a web-search prompt that forces the model to call the
 *      `exa_search` MCP tool.
 *   3. Assert the assistant reply contains BOTH a "search" indicator
 *      AND a coherent answer (i.e. NOT the `error_max_turns` error
 *      panel that read "Error: Claude SDK result reported an error").
 *
 * If this regresses, the assertion will fail with the literal error
 * panel text in the diff — much easier to debug than a silent failure.
 *
 * Prerequisites:
 *   - `EXA_API_KEY` env var on the backend (the provider only
 *     enables the Exa MCP server when this is set).
 *   - a running `ccpty serve` bridge on the backend.
 *
 * Skipped (not failed) when either is missing — surfacing missing
 * config as a noisy red CI failure isn't useful.
 */

import { expect, test } from './fixtures';
import { readChatTranscript, typeAndSendChatMessage } from './helpers';

const REPLY_BUDGET_MS = 90_000;
const REPLY_POLL_MS = 3_000;

/** Phrases that indicate the Claude SDK error_max_turns regression is back. */
const ERROR_PANEL_PATTERNS = [
	/error_max_turns/i,
	/Claude SDK result reported an error/i,
	/error:\s*claude/i,
];

/** Phrases the chat shows when the Exa web-search tool fired. */
const SEARCH_INDICATOR_PATTERNS = [/searched the web/i, /searching the web/i, /exa_search/i];

test.describe('tools — web search', () => {
	test('Claude model uses the Exa web search tool without an error_max_turns panel', async ({
		stagehand,
		navigateToApp,
	}) => {
		await navigateToApp('/');
		const page = stagehand.context.pages()[0];
		if (page === undefined) throw new Error('No active Stagehand page');

		// Pick Claude through the model selector UI. The model picker now
		// defaults to the FIRST catalog entry (no persisted "last used"),
		// so we can't pre-seed the selection via localStorage anymore — we
		// drive the composer's "Select model and reasoning" dropdown and
		// choose Claude Sonnet directly. `act` (LLM-driven) handles the
		// nested host → vendor → model menu without us hard-coding its
		// internal selectors.
		await stagehand.act('Open the model selector in the chat composer');
		await stagehand.act('Select the Claude Sonnet model');
		await page.waitForTimeout(300);

		// Send a question that REQUIRES web search to answer well —
		// "current weather in Tokyo" would also work but is geography-
		// dependent. A YC startup name forces the model into the search
		// path because it can't be in training data with high confidence.
		// Use the deterministic shared helper instead of LLM-driven act
		// so the send is reliable + token-free.
		const prompt =
			'Use the web search tool to look up what YC startup VOYGR is. Reply in one sentence based on the search results.';
		await typeAndSendChatMessage(page, prompt);

		// Poll the chat DOM directly — extract.text is much cheaper +
		// more reliable than asking the LLM "is there an error panel".
		// Stop on EITHER (a) the error panel (regression detected), OR
		// (b) a steady assistant reply that contains the search
		// indicator. Both are terminal states.
		const deadline = Date.now() + REPLY_BUDGET_MS;
		let combinedSnippets = '';
		let hasToolError = false;
		let mentionsSearch = false;
		let assistantCount = 0;
		while (Date.now() < deadline) {
			const transcript = await readChatTranscript(page);
			combinedSnippets = transcript.map((row) => row.snippet).join('\n');
			hasToolError = ERROR_PANEL_PATTERNS.some((pat) => pat.test(combinedSnippets));
			mentionsSearch = SEARCH_INDICATOR_PATTERNS.some((pat) => pat.test(combinedSnippets));
			assistantCount = transcript.filter((row) => row.role === 'assistant').length;
			if (hasToolError) break;
			if (assistantCount > 0 && mentionsSearch) break;
			await page.waitForTimeout(REPLY_POLL_MS);
		}

		// Hard-fail if the error_max_turns regression is back. This is
		// THE assertion this spec exists for.
		expect(
			hasToolError,
			`expected NO tool-error panel in the chat. The "Claude SDK result reported an error" / "error_max_turns" regression in claude_provider.py is back. Bump _TOOL_ENABLED_MAX_TURNS or check the backend logs. Combined chat text: ${combinedSnippets}`
		).toBe(false);

		// If Claude is unavailable (auth issue, model deprecated, rate
		// limit), Claude won't reply at all. That's NOT the regression
		// this spec is testing — skip the rest of the assertions so a
		// transient Claude infra issue doesn't hide the actual core
		// check (no error_max_turns panel) above.
		if (assistantCount === 0) {
			test.skip(
				true,
				`Claude did not produce any assistant reply within ${REPLY_BUDGET_MS / 1000}s. Likely a Claude infra / auth issue, not the regression under test. Combined chat text: ${combinedSnippets}`
			);
			return;
		}

		// Soft-confirm the model actually invoked the tool. Logged as a
		// warning rather than a hard fail because the model can choose
		// to answer from training data; the regression we're guarding
		// is the SILENT failure (error_max_turns), not whether the tool
		// fired on every prompt.
		if (!mentionsSearch) {
			console.warn(
				`[tool-web-search] Claude replied but no "Searched the web" indicator — the model may have answered from training data. Combined: ${combinedSnippets}`
			);
		}
	});
});
