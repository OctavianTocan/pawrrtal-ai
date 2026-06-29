---
name: api-setup-not-ui
paths: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "**/playwright.config.*"]
---

# API Setup, Not UI Setup in Playwright

Don't click through the UI to set up test data. Use `request` context to
hit APIs directly. UI setup is slow, flaky, and couples every test to
unrelated UI flows — if the signup form breaks, every test fails.

## Verify

"Am I clicking through a login/signup/creation flow just to set up state
for the actual test? Can I use `request.post()` or `request.fetch()`
instead?"

## Patterns

Bad — every test clicks through login:

```ts
await page.goto('/login');
await page.fill('#email', 'test@example.com');
await page.fill('#password', 'password');
await page.click('button[type=submit]');
await page.waitForURL('/dashboard');
```

Good — API setup, test starts at the actual page:

```ts
const response = await request.post('/api/auth/login', {
  data: { email: 'test@example.com', password: 'password' },
});
const { token } = await response.json();
await page.goto('/dashboard', {
  headers: { Authorization: `Bearer ${token}` },
});
```
