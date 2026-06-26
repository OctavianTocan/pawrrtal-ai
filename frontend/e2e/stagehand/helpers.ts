/**
 * Shared E2E helpers used across multiple Stagehand specs.
 *
 * Anything in this file should be deterministic / Playwright-style
 * (no LLM round-trip) — these are the building blocks specs use to
 * set up state without burning Stagehand tokens. LLM-driven actions
 * (`act`, `observe`, `extract`) belong in the spec files.
 */

import type { Page, Stagehand } from '@browserbasehq/stagehand';
import { z } from 'zod';

const REPLY_POLL_MS = 2_500;

/**
 * Type a message into the chat composer and submit the form.
 *
 * Why bypass Stagehand's `act` for this:
 *   1. The chat composer (`features/chat/components/ChatComposer.tsx`)
 *      uses a controlled `<textarea name="message">` whose value is
 *      driven by React state. The form's onSubmit handler reads
 *      `new FormData(form).get('message')` which sees the DOM value,
 *      but React's controlled-input mechanism resets the value back
 *      to the prior state if `onChange` doesn't fire properly.
 *   2. Stagehand's `act("Type ... press Enter")` sometimes targets
 *      the wrong button (model selector, voice input, attachments)
 *      which silently no-ops the send.
 *
 * This helper uses `page.locator(textarea).fill(text)` (Playwright-
 * style — fires React-aware events) then triggers `form.requestSubmit()`
 * via `page.evaluate`. Reliable across runs and zero LLM tokens.
 *
 * @param page - The Stagehand-wrapped Playwright page.
 * @param text - The message content to send.
 */
export async function typeAndSendChatMessage(page: Page, text: string): Promise<void> {
  const textarea = page.locator('textarea[name="message"]');
  await textarea.fill(text);
  // One frame for React to flush the controlled state update from
  // the input event before we submit. Without this gap the form
  // reads stale (empty) state and sends an empty user message.
  await page.waitForTimeout(150);
  await page.evaluate(() => {
    const ta = document.querySelector<HTMLTextAreaElement>('textarea[name="message"]');
    const form = ta?.closest('form');
    if (form === null || form === undefined) {
      throw new Error('Could not find chat composer form to submit');
    }
    form.requestSubmit();
  });
  // Settle wait so subsequent polling doesn't race the just-sent
  // state machine before the user message renders.
  await page.waitForTimeout(300);
}

/** Schema returned by `readChatTranscript`. */
const TranscriptRowSchema = z.object({
  role: z.enum(['user', 'assistant']),
  snippet: z.string(),
});
export type ChatTranscriptRow = z.infer<typeof TranscriptRowSchema>;

/**
 * Read the chat transcript directly from the DOM (no LLM extract).
 *
 * Each chat row is rendered via the `Message` component
 * (`components/ai-elements/message.tsx`) which applies either
 * `is-user` or `is-assistant` to its root div. Reading via these
 * classes is faster (no LLM token spend) and more reliable than
 * `stagehand.extract` — extract was pulling prompt-suggestion buttons
 * and other non-message UI into the result.
 *
 * @param page - The Stagehand-wrapped Playwright page.
 * @returns Array of `{ role, snippet }` rows in DOM order.
 */
export async function readChatTranscript(page: Page): Promise<ChatTranscriptRow[]> {
  return await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll<HTMLElement>('.is-user, .is-assistant'));
    return rows.map((row) => ({
      role: row.classList.contains('is-user') ? ('user' as const) : ('assistant' as const),
      snippet: (row.textContent ?? '').trim().slice(0, 500),
    }));
  });
}

/**
 * Repeatedly read the chat transcript until the assistant has
 * produced at least `minAssistantCount` non-placeholder turns, OR
 * `budgetMs` elapses.
 *
 * The "non-placeholder" check strips leading non-letter characters
 * (the loader spinner uses braille chars like ⠸ as a prefix) and
 * tests for the literal "Thinking" placeholder. Without this strip
 * the regex would fail on `⠸Thinking...` and the poll would exit
 * while the model is still streaming, returning the placeholder as
 * the answer.
 *
 * @param stagehand - Live Stagehand instance.
 * @param options.budgetMs - Hard ceiling on total wait time.
 * @param options.minAssistantCount - Minimum number of completed
 *   assistant turns to wait for. Defaults to 1.
 * @throws Error when the budget elapses without a reply.
 */
export async function pollForAssistantReply(
  stagehand: Stagehand,
  options: { budgetMs: number; minAssistantCount?: number }
): Promise<ChatTranscriptRow[]> {
  const minAssistantCount = options.minAssistantCount ?? 1;
  const deadline = Date.now() + options.budgetMs;
  const page = stagehand.context.pages()[0];
  if (page === undefined) throw new Error('No active Stagehand page');

  let lastTranscript: ChatTranscriptRow[] = [];
  while (Date.now() < deadline) {
    lastTranscript = await readChatTranscript(page);
    const assistantTurns = lastTranscript.filter((m) => m.role === 'assistant');
    const latestAssistantSnippet = assistantTurns[assistantTurns.length - 1]?.snippet ?? '';
    const trimmedSnippet = latestAssistantSnippet.replace(/^[^A-Za-z]+/, '').trim();
    const isStillThinking = /^thinking/i.test(trimmedSnippet);
    const hasMinAssistant = assistantTurns.length >= minAssistantCount && !isStillThinking;
    if (hasMinAssistant) return lastTranscript;
    await page.waitForTimeout(REPLY_POLL_MS);
  }
  throw new Error(
    `No assistant reply within ${options.budgetMs / 1000}s budget. Last transcript: ${JSON.stringify(lastTranscript)}`
  );
}
