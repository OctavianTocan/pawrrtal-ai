---
name: fire-analytics-in-all-paths
paths: ["**/*.ts", "**/*.tsx"]
---

# Fire Analytics in All Paths

Analytics events must be fired in ALL code paths: success, error, and loading/loading-states. Never gate analytics behind success-only branches. If a feature has a try/catch, both branches emit events.

**Why:** Success-only analytics creates blind spots. You can't measure failure rates, error patterns, or user drop-off from error states if those events are never emitted.

**Learned from:** the vendored app — AGENTS.md convention.

## Verify

"Does every try/catch fire analytics in BOTH the try and catch branches? Are loading-state transitions tracked too? Is there any code path where a user action goes unmeasured?"

## Patterns

Bad — analytics only on success, errors are invisible:

```typescript
async function submitForm(data: FormData) {
  try {
    const result = await api.submit(data);
    analytics.track('form_submitted', { status: 'success', id: result.id });
  } catch (error) {
    // no analytics → can't measure failure rate
    showErrorToast(error);
  }
}
```

Good — analytics in every branch:

```typescript
async function submitForm(data: FormData) {
  analytics.track('form_submit_started', { fields: Object.keys(data) });
  try {
    const result = await api.submit(data);
    analytics.track('form_submitted', { status: 'success', id: result.id });
  } catch (error) {
    analytics.track('form_submitted', {
      status: 'error',
      error: error instanceof Error ? error.message : 'unknown',
    });
    showErrorToast(error);
  }
}
```
