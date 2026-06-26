/**
 * Chat — multi-turn end-to-end with assistant-reply assertion and
 * message-action exercise. Proves the chat actually WORKS, not just
 * that the composer renders text.
 *
 * Coverage:
 *   1. **Multi-turn round-trip** — send a math question, wait for the
 *      assistant reply, assert it contains the correct number, send a
 *      follow-up that depends on context, assert the second reply uses
 *      the first answer (proves conversation memory).
 *
 *   2. **Modal handling** — dismiss any open onboarding/welcome dialog
 *      via Stagehand `act` (Radix dialogs honor Escape; a single
 *      `act("press Escape")` covers both real-Radix and any other
 *      dismiss mechanism the LLM finds).
 *
 *   3. **Wait for reply** — poll-extract loop with a hard budget. Real
 *      assistant responses can take 2-30s depending on the backend
 *      provider; we extract the transcript every 2s and stop as soon
 *      as the assistant turn appears.
 *
 *   4. **Message actions** — after a successful reply, observe the
 *      action buttons that hover-reveal on the assistant message
 *      (copy, regenerate, etc.) and assert at least one is present.
 *
 *   5. **Stagehand patterns shown**: `observe`+`act` with cached
 *      action, `act` with `%variables%` (cache-friendly typing),
 *      array `extract` with discriminated role enum, scoped extract
 *      via the messages container.
 *
 * Why no multi-model loop in this file: one provider per test run is
 * cheaper to debug. Use `STAGEHAND_MODELS=openai/gpt-4.1-mini,google/
 * gemini-3.1-pro-preview just stagehand-e2e` if you want to sweep
 * multiple providers in CI — the fixture honors `STAGEHAND_MODEL`
 * override.
 */

import { expect, test } from './fixtures';
import { pollForAssistantReply, typeAndSendChatMessage } from './helpers';

const REPLY_BUDGET_MS = 60_000;

// Onboarding is auto-suppressed by the fixture's `addInitScript` that
// sets `pawrrtal:e2e-skip-onboarding=1` in localStorage before any
// page script runs (see `fixtures.ts` and
// `features/onboarding/v2/OnboardingFlow.tsx`). The first paint lands
// on a clean chat surface with no modal in the way — no per-spec
// dismiss workaround needed.
test.describe('chat', () => {
  test('multi-turn round-trip with assistant replies and message actions', async ({ stagehand, navigateToApp }) => {
    // Open a fresh conversation route so we get a brand-new UUID
    // and a clean transcript every time.
    await navigateToApp('/');
    const page = stagehand.context.pages()[0];
    if (page === undefined) throw new Error('No active Stagehand page');

    // === Turn 1 ===
    // Use a question with a deterministic numeric answer so we can
    // assert on the reply without relying on LLM creativity.
    //
    // We pass a plain string for the type instruction so Stagehand
    // can re-plan on cache miss (cached actions bypass self-heal).
    // For the SEND we go around Stagehand entirely and submit the
    // composer form via page.evaluate — the LLM was sometimes
    // targeting the wrong button (model selector, voice input,
    // etc.) and either no-op'ing or sending an empty message. A
    // direct form submit is what the textarea's Enter handler
    // would do anyway, so this matches real user behavior without
    // the targeting risk.
    const turn1 = 'What is seven plus five? Reply with just the number.';
    await typeAndSendChatMessage(page, turn1);

    // Poll-extract loop: wait until the assistant turn shows up.
    const transcript1 = await pollForAssistantReply(stagehand, { budgetMs: REPLY_BUDGET_MS });

    // User message must be present and assistant must have replied.
    const userTurns1 = transcript1.filter((m) => m.role === 'user');
    const assistantTurns1 = transcript1.filter((m) => m.role === 'assistant');
    expect(
      userTurns1.some((m) => m.snippet.toLowerCase().includes('seven plus five')),
      `expected user turn 1 to contain the question. Got: ${JSON.stringify(transcript1, null, 2)}`
    ).toBe(true);
    expect(
      assistantTurns1.length,
      `expected an assistant reply within ${REPLY_BUDGET_MS / 1000}s. Got transcript: ${JSON.stringify(transcript1, null, 2)}`
    ).toBeGreaterThan(0);
    const assistant1Snippet = assistantTurns1.map((m) => m.snippet).join(' ');
    expect(assistant1Snippet.includes('12'), `expected the assistant to answer 12. Got: ${assistant1Snippet}`).toBe(
      true
    );

    // === Turn 2 — context-dependent follow-up ===
    // A correct answer to "multiply that by 3" requires the assistant
    // to remember the prior turn's answer (12). Proves conversation
    // memory works.
    const turn2 = 'Multiply that by three. Reply with just the number.';
    await typeAndSendChatMessage(page, turn2);

    const transcript2 = await pollForAssistantReply(stagehand, {
      budgetMs: REPLY_BUDGET_MS,
      minAssistantCount: assistantTurns1.length + 1,
    });

    const assistantTurns2 = transcript2.filter((m) => m.role === 'assistant');
    expect(
      assistantTurns2.length,
      `expected a second assistant reply. Got: ${JSON.stringify(transcript2, null, 2)}`
    ).toBeGreaterThanOrEqual(assistantTurns1.length + 1);
    const assistant2LatestSnippet = assistantTurns2[assistantTurns2.length - 1]?.snippet ?? '';
    expect(
      assistant2LatestSnippet.includes('36'),
      `expected the second assistant reply to use the first answer (12 * 3 = 36). Got: ${assistant2LatestSnippet}`
    ).toBe(true);

    // === Message actions ===
    // Hover-reveal action buttons on the latest assistant message.
    // Stagehand's observe surfaces interactable elements; we just
    // assert at least one of the canonical actions is reachable.
    const actionsObservation = await stagehand.observe(
      'Find the action buttons (such as Copy, Regenerate, Like, Dislike) on the most recent assistant message'
    );
    expect(
      actionsObservation.length,
      'expected at least one message-action button on the latest assistant message'
    ).toBeGreaterThan(0);
  });
});

// `typeAndSendChatMessage` and `pollForAssistantReply` live in
// `./helpers.ts` so other specs (sidebar-new-session, web-search, ...)
// can reuse the same chat-send path without copy-pasting fragile React
// interaction logic.
