/**
 * Add Workspace onboarding — opens via the workspace selector dropdown.
 *
 * The legacy `OnboardingModal` (`features/onboarding/OnboardingModal.tsx`)
 * is mounted at the app-layout level with `initialOpen=false` and only
 * opens when the user clicks "Add Workspace..." in the workspace
 * selector dropdown. It's a 3-step flow:
 *
 *   1. **Welcome** — overview of workspace categories. Button: "Get started"
 *   2. **Create workspace** — pick "Create new" or "Connect to remote server"
 *   3. **Local workspace** — folder picker. Button: finish (closes modal)
 *
 * Why this is a separate spec from `onboarding.stagehand.spec.ts`: the
 * v2 OnboardingFlow auto-opens on every page load, but this Add
 * Workspace flow is event-driven. Different entry points = different
 * tests = independent failure isolation.
 *
 * Coverage gap: backend persistence isn't asserted (the flow is
 * cosmetic — no workspace gets saved, per the component docstring).
 * This spec only proves the UI flow can be navigated.
 */

import { z } from 'zod';
import { expect, test } from './fixtures';

// The fixture's `addInitScript` already suppresses the v2
// OnboardingFlow before this spec lands on /, so the workspace
// selector dropdown opens cleanly from the very first interaction.
// We're testing the SEPARATE legacy `OnboardingModal` (workspace
// onboarding) that's event-driven from the dropdown — it's unaffected
// by the skip flag.
test.describe('add workspace', () => {
  test('opens via workspace selector and walks through all 3 steps', async ({ stagehand, navigateToApp }) => {
    await navigateToApp('/');
    const page = stagehand.context.pages()[0];
    if (page === undefined) throw new Error('No active Stagehand page');
    await page.waitForTimeout(400);

    // Open the workspace selector dropdown in the sidebar.
    await stagehand.act('Click the workspace selector at the top of the left sidebar');
    await page.waitForTimeout(300);

    // Click "Add Workspace..." — fires OPEN_ONBOARDING_EVENT, which
    // the legacy OnboardingModal listens for.
    await stagehand.act("Click the 'Add Workspace...' menu item in the dropdown");
    await page.waitForTimeout(400);

    // === Step 1: Welcome ===
    await stagehand.act("Click the 'Get started' button");
    await page.waitForTimeout(300);

    // === Step 2: Create workspace ===
    // Two options: "Create new" or "Connect to remote server".
    // "Create new" leads to the local-folder step which has a
    // concrete finish button.
    await stagehand.act("Click the 'Create new' workspace option");
    await page.waitForTimeout(300);

    // === Step 3: Local workspace ===
    // The finish button is `disabled={!isFolderSelected}` (per
    // `onboarding-local-workspace-step.tsx:145`). The folder pick
    // goes through a hidden `<input type=file webkitdirectory>`
    // which Playwright headless can't drive without a real OS
    // chooser. Instead of trying to close the modal, we assert
    // we successfully REACHED Step 3 — proves the flow opens via
    // the workspace selector, navigates Welcome → Create → Local,
    // and shows the folder-pick affordance.
    const { hasFolderPicker } = await stagehand.extract(
      'Is there a button or affordance for selecting a local folder / directory visible in the modal right now?',
      z.object({
        hasFolderPicker: z
          .boolean()
          .describe(
            'True if a "Select folder", "Choose folder", or similar folder-picker control is visible in the open modal'
          ),
      })
    );
    expect(hasFolderPicker, 'expected to reach Step 3 (Local workspace) with a folder-picker control visible').toBe(
      true
    );
  });
});
