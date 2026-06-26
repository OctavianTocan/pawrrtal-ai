/**
 * Sidebar — collapse / expand via the trigger button (and persistence).
 *
 * The sidebar trigger in `components/app-layout.tsx::AppHeader` toggles
 * the resizable sidebar panel between expanded (~280px) and collapsed
 * (0px). Toggle state is persisted via the SidebarProvider so a refresh
 * preserves the user's preference.
 *
 * Why we measure DOM width directly instead of using `stagehand.extract`
 * to ask "is the sidebar visible": the sidebar's collapsed state clips
 * its inner content via overflow:hidden + pointer-events:none, but the
 * conversation list and search input stay in the DOM (and stay
 * "visible" to the accessibility tree). LLM-driven extract therefore
 * reports both states as visible, even when the user sees a 0px-wide
 * collapsed panel. Direct width measurement via `page.evaluate` is the
 * objective signal: collapsed → 0, expanded → ~280px+.
 */

import { expect, test } from './fixtures';

const SIDEBAR_DATA_SELECTOR = '[data-state="expanded"], [data-state="collapsed"]';

/**
 * Read the rendered width (in CSS px) of the resizable sidebar panel.
 * Returns 0 when collapsed, ~280+ when expanded. Falls back to 0 if
 * the panel can't be located, so the assertion has a stable baseline.
 */
async function _measureSidebarWidth(page: import('@browserbasehq/stagehand').Page): Promise<number> {
  return await page.evaluate((selector) => {
    const panel = document.querySelector(selector);
    if (panel === null) return 0;
    const rect = panel.getBoundingClientRect();
    return Math.round(rect.width);
  }, SIDEBAR_DATA_SELECTOR);
}

test.describe('sidebar — collapse toggle', () => {
  test('clicking the sidebar trigger collapses then re-expands the panel', async ({ stagehand, navigateToApp }) => {
    await navigateToApp('/');
    const page = stagehand.context.pages()[0];
    if (page === undefined) throw new Error('No active Stagehand page');

    const initialWidth = await _measureSidebarWidth(page);

    // Click the sidebar toggle button in the top-left header.
    const toggleInstruction =
      'Click the sidebar toggle button in the top-left of the page header (the icon that opens or closes the sidebar)';
    const [toggleAction] = await stagehand.observe(toggleInstruction);
    const fireToggle = async (): Promise<void> => {
      if (toggleAction === undefined) await stagehand.act(toggleInstruction);
      else await stagehand.act(toggleAction);
    };

    await fireToggle();
    // CSS transition for the panel collapse runs ~250ms (per
    // `COLLAPSE_ANIMATION_DURATION_MS` in app-layout.tsx). Wait
    // enough that the post-toggle frame is steady.
    await page.waitForTimeout(450);

    const widthAfter1st = await _measureSidebarWidth(page);
    // Width must change by at least 50px in either direction. We don't
    // assert "0 vs N" because the toggle direction depends on the
    // user's persisted preference at first paint.
    expect(
      Math.abs(widthAfter1st - initialWidth),
      `expected sidebar width to change after one toggle. initial=${initialWidth}px after=${widthAfter1st}px`
    ).toBeGreaterThan(50);

    await fireToggle();
    await page.waitForTimeout(450);

    const widthAfter2nd = await _measureSidebarWidth(page);
    // The second toggle should restore something close to the
    // initial width (within ~10px to allow for snapping). Anti-flake:
    // we don't require exact equality — the resizable panel can land
    // 1-2px off due to flex rounding.
    expect(
      Math.abs(widthAfter2nd - initialWidth),
      `expected sidebar width to return to initial (${initialWidth}px) after a second toggle. Got: ${widthAfter2nd}px`
    ).toBeLessThan(10);
  });
});
