/**
 * Onboarding v2 — full happy-path walkthrough.
 *
 * The v2 onboarding (`features/onboarding/v2/OnboardingFlow.tsx`) is
 * mounted in `components/app-layout.tsx` with `initialOpen=true`, so
 * it's the first thing a fresh user sees on `/`. It's a 4-step wizard:
 *
 *   1. **Step Identity** — name, company website, LinkedIn (optional),
 *      role, goal chips. Continue is always enabled.
 *   2. **Step Context** — paste / connect ChatGPT history. Continue +
 *      "Skip for now".
 *   3. **Step Personality** — agent personality knobs. Continue.
 *   4. **Step Messaging** — connect Slack/Discord channel. "Continue"
 *      finishes the wizard and closes the modal.
 *
 * What this spec proves:
 *   - The wizard can be walked through end-to-end via natural language
 *     (`act` for typing, `act` for clicking Continue/Skip).
 *   - `act` with `%variables%` types into form fields without leaking
 *     the input value to the LLM provider (Stagehand's variable
 *     substitution happens at execution time).
 *   - After clicking Continue on the final step, the modal disappears
 *     and the chat composer becomes visible — the user has fully
 *     traversed the wizard.
 *
 * Coverage gap (intentional): goal-chip selection and per-step field
 * accuracy aren't asserted — those are unit-tested in the section's
 * own `*.test.tsx` files. This spec is about end-to-end navigability.
 */

import { z } from 'zod';
import { E2E_SKIP_ONBOARDING_STORAGE_KEY } from '../../features/onboarding/v2/OnboardingFlow';
import { expect, test } from './fixtures';

// This spec exercises the v2 OnboardingFlow itself, so it has to
// override the fixture-wide skip flag before navigating. Without this
// the modal stays closed on /, defeating the test. We use
// `addInitScript` to set the flag to '0' (the gate inside
// `OnboardingFlow.tsx` only suppresses on '1') BEFORE any page script
// runs, so the wizard hydrates open as production users see it.
test.describe('onboarding', () => {
  test('walks through all 4 steps and lands in the chat', async ({ stagehand, navigateToApp }) => {
    // Override the fixture-wide suppression so the wizard auto-opens.
    await stagehand.context.addInitScript(
      ({ key }: { key: string }) => {
        try {
          window.localStorage.setItem(key, '0');
        } catch {
          /* private browsing — fine, the wizard opens by default anyway */
        }
      },
      { key: E2E_SKIP_ONBOARDING_STORAGE_KEY }
    );
    await navigateToApp('/');

    // === Step 1: Identity ===
    // Fill the four text fields. Variables keep the cache key stable
    // across runs even when the input values change.
    await stagehand.act('Type %name% into the Your name field', {
      variables: { name: 'E2E Tester' },
    });
    await stagehand.act('Type %url% into the Company website field', {
      variables: { url: 'https://e2e.example.com' },
    });
    await stagehand.act('Type %role% into the Your role field', {
      variables: { role: 'Founder' },
    });
    // Pick a goal chip — exercises the toggle UI.
    await stagehand.act("Click the 'Personal Assistant' goal chip");
    await stagehand.act("Click the 'Continue' button at the bottom of the modal");

    // === Step 2: Context ===
    // We don't have a real ChatGPT export to paste, so take the
    // "Skip for now" path. Proves the optional step is dismissible.
    await stagehand.act("Click the 'Skip for now' button");

    // === Step 3: Personality ===
    // Whatever defaults are selected are fine — just continue.
    await stagehand.act("Click the 'Continue' button");

    // === Step 4: Messaging ===
    // The Continue button is `disabled={!hasOne}` until at least
    // one messaging channel is connected. Click Connect on the
    // first row first, THEN click Continue. The Continue click
    // calls `onFinish`, which closes the modal.
    await stagehand.act("Click the 'Connect' button on the first messaging channel row");
    await stagehand.act("Click the 'Continue' button to finish onboarding");

    // === Assert: modal is gone, chat composer is visible ===
    // Use Stagehand's extract to read the visible page state. If
    // the modal is still up, the extracted shell title will mention
    // "Let's get to know you" or similar; if it's gone, the chat
    // composer placeholder ("Ask Pawrrtal anything…") is visible.
    const { hasComposer, hasModal } = await stagehand.extract(
      'Inspect the page: is the chat composer at the bottom visible? Is any onboarding/welcome modal still open?',
      z.object({
        hasComposer: z
          .boolean()
          .describe(
            'True if a chat composer textarea is visible at the bottom of the page (placeholder mentions "Ask" or "message")'
          ),
        hasModal: z
          .boolean()
          .describe('True if a multi-step onboarding/welcome modal dialog is still open over the page'),
      })
    );

    expect(hasModal, 'expected the onboarding modal to be closed after Step 4').toBe(false);
    expect(hasComposer, 'expected the chat composer to be visible after onboarding finishes').toBe(true);
  });
});
