/**
 * Settings page — observe-then-act over a single nav tab, then
 * structured extract of the heading.
 *
 * What this exercises:
 *   - Stagehand initializes with the dev-admin cookie pre-loaded
 *   - `observe` returns a cacheable Action for the nav click
 *   - `act` executes the cached action
 *   - `extract` reads the right-pane heading via a Zod schema
 *
 * Patterns to keep:
 *   - Atomic `act` strings ("Click the X item")
 *   - Plan-then-act with `observe` so the action is replayable + cached
 *     (per .claude/rules/stagehand/stagehand-v3-typescript-patterns.md)
 *   - Use the shared `navigateToApp` helper, not raw page.goto, so the
 *     suite always waits for networkidle (required for cache hits per
 *     Stagehand's caching docs).
 */

import { z } from 'zod';
import { expect, test } from './fixtures';

test.describe('settings page', () => {
  test('navigates to Appearance and shows the matching heading', async ({ stagehand, navigateToApp }) => {
    await navigateToApp('/settings');

    // Plan-then-act with `observe` is the cache-friendly pattern,
    // but some models (e.g. Gemini 3.1 Pro Preview) occasionally
    // return zero observed elements on the first pass. Fall back
    // to a direct `act` in that case — Stagehand's act path uses
    // the same a11y tree internally and reliably finds the element.
    const instruction = "Click the 'Appearance' item in the left navigation rail";
    const [clickAppearance] = await stagehand.observe(instruction);
    if (clickAppearance === undefined) {
      await stagehand.act(instruction);
    } else {
      await stagehand.act(clickAppearance);
    }

    const { heading } = await stagehand.extract(
      'Read the H1 heading currently shown in the settings detail pane',
      z.object({ heading: z.string() })
    );

    // The "Appearance" nav item opens the section whose H1 is "Theme"
    // (the design labels the nav item by category, the heading by
    // the actual control on screen).
    expect(heading.toLowerCase()).toContain('theme');
  });
});
