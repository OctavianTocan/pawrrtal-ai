---
name: web-first-assertions
paths: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "**/playwright.config.*"]
---

# Web-First Assertions in Playwright

Use web-first assertions (`expect(locator).toBeVisible()`,
`.toHaveText()`, `.toBeEnabled()`, etc.) instead of extracting a boolean
and asserting on it. Web-first assertions auto-retry until timeout,
eliminating flakiness from timing issues.

## Verify

"Am I using `expect(someBool).toBe(true)` or `expect(await loc.isVisible()).toBe(true)`?
Replace with `await expect(loc).toBeVisible()`."

## Patterns

Bad — no auto-retry, instant pass/fail:

```ts
const visible = await page.locator('.toast').isVisible();
expect(visible).toBe(true);
```

Good — auto-retries until visible or timeout:

```ts
await expect(page.getByText('Saved successfully')).toBeVisible();
```

Bad — checking text content manually:

```ts
const text = await page.locator('.count').textContent();
expect(text).toBe('5');
```

Good — retries until text matches:

```ts
await expect(page.locator('.count')).toHaveText('5');
```
