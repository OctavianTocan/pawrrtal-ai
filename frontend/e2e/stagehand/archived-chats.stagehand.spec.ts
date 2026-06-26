/**
 * Archived chats tab — discriminated extract for empty vs populated.
 *
 * Demonstrates Stagehand's discriminated-union pattern: the page
 * shows EITHER an empty state OR a list of archived chats. We let
 * Stagehand decide which mode the page is in, then assert the
 * appropriate shape.
 *
 * The Playwright equivalent in `frontend/e2e/settings.spec.ts` uses
 * `expect(unarchive.or(empty)).toBeVisible()`. Same intent, but here
 * we additionally extract the count so failures point at "expected
 * empty or list, got header but no children" not "selector missed".
 */

import { z } from 'zod';
import { expect, test } from './fixtures';

const StateSchema = z.object({
  mode: z
    .enum(['empty', 'populated'])
    .describe(
      "'empty' if the panel shows a no-archived-chats placeholder; 'populated' if it shows at least one archived chat row with an Unarchive button"
    ),
  count: z.number().describe('Number of archived chat rows visible. 0 when mode is empty.'),
});

test.describe('archived chats', () => {
  test('renders either an empty state or a populated list', async ({ stagehand, navigateToApp }) => {
    await navigateToApp('/settings');

    const [clickArchived] = await stagehand.observe("Click the 'Archived chats' item in the left navigation rail");
    if (clickArchived === undefined) {
      throw new Error("observe() returned no actions for the 'Archived chats' nav click");
    }
    await stagehand.act(clickArchived);

    const state = await stagehand.extract(
      'Inspect the archived-chats panel and report whether it is empty or populated, plus the row count.',
      StateSchema
    );

    // Discriminated assertion — both branches are valid; the row
    // count must agree with the mode.
    if (state.mode === 'empty') {
      expect(state.count).toBe(0);
    } else {
      expect(state.count).toBeGreaterThan(0);
    }
  });
});
