---
name: role-selectors
paths: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "**/playwright.config.*"]
---

# Role Selectors Over CSS in Playwright

Use `page.getByRole()`, `page.getByText()`, `page.getByLabel()`, and
`page.getByPlaceholder()` instead of CSS selectors. Role-based locators
survive refactors (class renames, DOM restructuring) and test the page
the way a real user or screen reader would find elements.

## Verify

"Am I using `.locator('.some-class')` or `#some-id`? Could I use
`getByRole`, `getByText`, or `getByLabel` instead?"

## Priority

1. `getByRole` — buttons, links, headings, textboxes (preferred)
2. `getByLabel` — form fields with labels
3. `getByPlaceholder` — inputs without visible labels
4. `getByText` — non-interactive elements by visible text
5. `getByTestId` — last resort when no semantic locator works

## Patterns

Bad — brittle, breaks on class rename:

```ts
await page.locator('.btn-primary.submit').click();
await page.locator('#email-input').fill('test@example.com');
```

Good — semantic, resilient:

```ts
await page.getByRole('button', { name: 'Submit' }).click();
await page.getByLabel('Email').fill('test@example.com');
```
