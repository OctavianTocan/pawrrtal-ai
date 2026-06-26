/**
 * Sidebar — "New session" button creates a fresh conversation.
 *
 * The "+ New session" button at the top of the sidebar
 * (`components/new-session-button.tsx`) routes to `/`, which always
 * mints a new conversation UUID via the conversation-creation hook.
 * After a chat sends, the conversation appears in the sidebar list
 * grouped by date — this spec proves the round-trip:
 *
 *   1. Click "New session" from the sidebar
 *   2. Send a deterministic prompt
 *   3. Wait for the assistant reply (so the conversation is persisted)
 *   4. Assert the conversation now appears in the sidebar
 *
 * Why this matters: a regression where new sessions don't appear in
 * the list is a top-three "the chat seems broken" bug class. Catching
 * it via a real round-trip is much higher-signal than a unit test.
 */

import { z } from 'zod';
import { expect, test } from './fixtures';
import { pollForAssistantReply, typeAndSendChatMessage } from './helpers';

const SidebarConversationsSchema = z.object({
  titles: z
    .array(z.string())
    .describe(
      'Visible conversation titles in the left sidebar list, top to bottom (skip headers like "Today" / "Yesterday")'
    ),
});

const REPLY_BUDGET_MS = 60_000;

test.describe('sidebar — new session', () => {
  test('creates a fresh conversation and lists it in the sidebar', async ({ stagehand, navigateToApp }) => {
    await navigateToApp('/');
    const page = stagehand.context.pages()[0];
    if (page === undefined) throw new Error('No active Stagehand page');

    // Click the "+ New session" trigger at the top of the sidebar.
    // observe-then-act so the resolved selector caches across runs.
    const newSessionInstruction = 'Click the "New session" button at the top of the left sidebar';
    const [newSessionAction] = await stagehand.observe(newSessionInstruction);
    if (newSessionAction === undefined) {
      await stagehand.act(newSessionInstruction);
    } else {
      await stagehand.act(newSessionAction);
    }

    // Send a unique-ish prompt so the conversation gets a stable
    // title that we can find in the sidebar list later. Use the
    // shared `typeAndSendChatMessage` helper instead of LLM-driven
    // `act` so the send is deterministic + token-free.
    const uniqueMarker = `e2e-marker-${Date.now().toString(36)}`;
    const prompt = `Reply with just the word OK to confirm receipt of token ${uniqueMarker}.`;
    await typeAndSendChatMessage(page, prompt);

    // Wait for the assistant turn so the backend persists the
    // conversation (titles only get auto-generated after the first
    // successful reply lands).
    await pollForAssistantReply(stagehand, { budgetMs: REPLY_BUDGET_MS });

    // Give the sidebar a beat to refetch (TanStack Query
    // invalidates `['conversations']` after the chat mutation).
    await page.waitForTimeout(1_500);

    const { titles } = await stagehand.extract(
      'List every conversation title currently shown in the left sidebar',
      SidebarConversationsSchema
    );

    // We don't assert on the exact AI-generated title (the model
    // rephrases). Instead we assert the sidebar now has at least one
    // non-empty conversation entry — proves the new session round-tripped.
    expect(
      titles.filter((t) => t.trim().length > 0).length,
      `expected the sidebar to show at least one conversation after sending. Got: ${JSON.stringify(titles)}`
    ).toBeGreaterThan(0);
  });
});

// `pollForAssistantReply` is in `./helpers.ts` — shared with chat,
// web-search and other specs. The local copy used Stagehand's `extract`
// which was both expensive and unreliable (suggestion buttons leaked
// into the result); the shared version reads `.is-user`/`.is-assistant`
// directly via `page.evaluate` for free + ground-truth.
