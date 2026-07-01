---
name: abort-error-is-expected
paths: ["**/*.{ts,tsx}"]
---
# Handle AbortError as Expected Flow

When using AbortController for fetch, SSE, or other async operations,
`AbortError` is an expected signal that the operation was intentionally
cancelled. Handle it separately from real errors. Don't log it, don't show
error UI, don't report it to Sentry.

## Verify

"Does this catch block handle AbortError separately? Will users see error
UI when they navigate away?"

## Patterns

Bad — fires error toast on normal navigation:

```typescript
try {
  const resp = await fetch(url, { signal: controller.signal });
} catch (error) {
  showErrorToast('Request failed');
  reportToSentry(error);
}
```

Good — silently handles expected cancellation:

```typescript
try {
  const resp = await fetch(url, { signal: controller.signal });
} catch (error) {
  if (error instanceof Error && error.name === 'AbortError') return;
  showErrorToast('Request failed');
  reportToSentry(error);
}
```
