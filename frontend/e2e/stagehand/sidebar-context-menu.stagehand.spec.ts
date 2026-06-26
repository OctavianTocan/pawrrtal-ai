/**
 * Sidebar — right-click context menu surfaces conversation actions.
 *
 * Each conversation row in the sidebar
 * (`features/nav-chats/components/ConversationSidebarItem.tsx`) opens
 * a context menu with the canonical row actions: Rename, Delete,
 * Archive, Mark unread, etc. Wired in
 * `features/nav-chats/hooks/use-conversation-actions.ts`.
 *
 * This spec proves the context menu opens AND surfaces the
 * canonical action set — without asserting on the exact label list,
 * so a Rename-only renaming or item reordering doesn't break the
 * test. We assert on a minimum set: { Rename, Delete } MUST be
 * present (those are the always-available actions).
 *
 * Prerequisite: the spec creates a conversation first via the chat
 * round-trip so there's a row to right-click. If a fresh test env
 * has no conversations, there's nothing to context-click.
 */

import { z } from 'zod';
import { expect, test } from './fixtures';
import { pollForAssistantReply, typeAndSendChatMessage } from './helpers';

const ContextMenuSchema = z.object({
  items: z
    .array(z.string())
    .describe(
      'Visible menu item labels in the open context menu (e.g. "Rename", "Delete", "Archive"), in the order they appear'
    ),
});

const REPLY_BUDGET_MS = 60_000;

test.describe('sidebar — context menu', () => {
  test('right-clicking a conversation surfaces Rename and Delete', async ({ stagehand, navigateToApp }) => {
    await navigateToApp('/');
    const page = stagehand.context.pages()[0];
    if (page === undefined) throw new Error('No active Stagehand page');

    // Seed a conversation so there's at least one row to right-click.
    // Cheap deterministic prompt; we don't care about the reply
    // content, only that the row appears in the sidebar.
    await typeAndSendChatMessage(page, 'Reply with just the word OK.');
    await pollForAssistantReply(stagehand, { budgetMs: REPLY_BUDGET_MS });
    await page.waitForTimeout(1_500);

    // Open the context menu on the most recent conversation row in
    // the sidebar. Stagehand's act for "right-click" maps to the
    // underlying contextmenu event the row registers.
    const openMenuInstruction =
      'Right-click the most recent conversation entry in the left sidebar to open its context menu';
    const [openMenuAction] = await stagehand.observe(openMenuInstruction);
    if (openMenuAction === undefined) {
      await stagehand.act(openMenuInstruction);
    } else {
      await stagehand.act(openMenuAction);
    }
    await page.waitForTimeout(300);

    const { items } = await stagehand.extract(
      'List every visible menu item label in the open context menu',
      ContextMenuSchema
    );

    const labels = items.map((label) => label.toLowerCase());
    expect(
      labels.some((label) => label.includes('rename')),
      `expected the context menu to include "Rename". Got: ${JSON.stringify(items)}`
    ).toBe(true);
    expect(
      labels.some((label) => label.includes('delete')),
      `expected the context menu to include "Delete". Got: ${JSON.stringify(items)}`
    ).toBe(true);
  });
});

// `pollForAssistantReply` lives in `./helpers.ts`.
