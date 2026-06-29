---
name: no-networkidle
paths: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "**/playwright.config.*"]
---

# No networkidle in Playwright

Never use `waitUntil: 'networkidle'` or `page.waitForLoadState('networkidle')`.
It's unreliable — any background polling, analytics, or websocket keeps the
network "busy" and causes random timeouts. Wait for the specific thing you
actually need instead.

## Verify

"Am I waiting for `networkidle`? What specific API response or DOM element
am I actually waiting for? Wait for that instead."

## Patterns

Bad — flaky, blocked by background requests:

```ts
await page.goto('/dashboard', { waitUntil: 'networkidle' });
```

Good — wait for the specific API response the page needs:

```ts
await page.goto('/dashboard');
await page.waitForResponse(resp =>
  resp.url().includes('/api/dashboard') && resp.status() === 200
);
```

Good — wait for the content that proves the page loaded:

```ts
await page.goto('/dashboard');
await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
```
