---
name: deduplicate-concurrent-token-refreshes
paths: ["**/*.{ts,tsx}"]
---
# Deduplicate Concurrent Token Refreshes With a Single In-Flight Promise

When multiple components call `getAccessToken({ forceRefresh: true })`
simultaneously, cache a single in-flight refresh promise and share it across
all callers. Without this, concurrent 401s trigger concurrent refreshes,
which race against each other and can invalidate tokens mid-flight.

## Verify

"Can multiple callers trigger simultaneous token refreshes? Is there a single
shared promise?"

## Patterns

Bad — 5 concurrent 401s trigger 5 refresh attempts:

```typescript
async function getToken() {
  if (isExpired(cached)) {
    cached = await refreshToken(); // Each caller gets its own refresh
  }
  return cached;
}
```

Good — single in-flight promise shared by all callers:

```typescript
let refreshPromise: Promise<string> | null = null;

async function getToken() {
  if (isExpired(cached)) {
    if (!refreshPromise) {
      refreshPromise = refreshToken().finally(() => {
        refreshPromise = null;
      });
    }
    cached = await refreshPromise;
  }
  return cached;
}
```
