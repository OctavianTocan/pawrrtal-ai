---
name: ordered-cleanup-sequence
paths: ["**/*.{ts,tsx}"]
---

# Ordered Cleanup and Logout Sequence

Multi-step cleanup operations (logout, session end, teardown) must execute
in a defined order because later steps depend on earlier ones. Document the
sequence explicitly. For logout: 1) Reset analytics (still has user context),
2) Clear caches/query data, 3) Sign out auth provider, 4) Notify extensions.

Running these out of order causes data leaks, orphaned analytics sessions,
and stale cache between users.

## Verify

"Does my cleanup sequence have a defined order? Could reordering steps cause
data loss or stale state?"

## Patterns

Bad — signs out first, loses analytics context:

```typescript
async function logout() {
  await signOut(auth);
  posthog.reset();
  queryClient.clear();
}
```

Good — strict order preserves context for each step:

```typescript
async function logout() {
  posthog.reset();                        // 1. Analytics (still has user)
  queryClient.clear();                    // 2. Clear cached data
  await signOut(auth);                    // 3. Sign out
  window.postMessage({ type: 'logout' }, window.location.origin); // 4. Notify extension
}
```
