---
name: timeout-async-auth
paths: ["**/*.{ts,tsx}"]
---
# Timeout All Async Auth Operations

`signInWithCustomToken`, `signInWithPopup`, and similar auth calls can hang
indefinitely on network issues, leaving the UI on a spinner forever. Wrap
them with a timeout (15s is reasonable) and transition to an error state
when it fires.

## Verify

"Can this auth operation hang forever? Does it have a timeout?"

## Patterns

Bad — hangs forever if Firebase is slow:

```typescript
async function login(token: string) {
  setLoading(true);
  const cred = await signInWithCustomToken(auth, token);
  setLoading(false);
  return cred;
}
```

Good — times out after 15 seconds, guards against late success:

```typescript
async function login(token: string) {
  setLoading(true);
  const attemptId = ++loginAttemptRef.current;
  try {
    const cred = await Promise.race([
      signInWithCustomToken(auth, token),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Auth timeout')), 15_000)
      ),
    ]);
    // Guard: if a newer attempt started, ignore this late result
    if (attemptId !== loginAttemptRef.current) return null;
    return cred;
  } catch (error) {
    if (attemptId !== loginAttemptRef.current) return null;
    setAuthError(error);
    throw error;
  } finally {
    if (attemptId === loginAttemptRef.current) setLoading(false);
  }
}
```

Note: `Promise.race` doesn't cancel the losing promise. If `signInWithCustomToken`
resolves after the timeout, it can still mutate global auth state. The attempt ID
guard prevents your UI from acting on stale results, but consider signing out
in the timeout path if your auth library has no cancellation API.
