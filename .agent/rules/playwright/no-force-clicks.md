---
name: no-force-clicks
paths: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "**/playwright.config.*"]
---

# No Force Clicks in Playwright

Never use `{ force: true }` on click actions. If a real user can't click
it, the test should fail — forcing hides actual UI bugs (overlapping
elements, missing scroll-into-view, z-index issues).

## Verify

"Am I using `{ force: true }` anywhere? If the click fails without it,
what's blocking the element — and shouldn't that be the real fix?"

## Patterns

Bad — forcing past a visibility issue:

```ts
await page.locator('.submit-btn').click({ force: true });
```

Good — fix the underlying issue or wait for visibility:

```ts
await page.getByRole('button', { name: 'Submit' }).click();
```
