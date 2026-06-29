---
name: reset-flags-in-finally
paths: ["**/*.ts", "**/*.tsx"]
---
# Reset Guard Flags in Finally Blocks

Any boolean flag or ref used to guard concurrent operations
(`isAuthenticatingRef`, `isLoadingRef`, mutex flags) must be reset in a
`finally` block, never only on the success path. If the flag is only reset
after success, any error permanently blocks subsequent operations.

## Verify

"Does every guard flag get reset on error paths too? Is the reset in a
`finally` block?"

## Patterns

Bad — flag stuck forever on error:

```typescript
const isAuthenticating = useRef(false);
async function login() {
  if (isAuthenticating.current) return;
  isAuthenticating.current = true;
  const result = await signInWithPopup(auth, provider);
  await finalizeLogin(result);
  isAuthenticating.current = false; // Never reached on error
}
```

Good — always resets:

```typescript
const isAuthenticating = useRef(false);
async function login() {
  if (isAuthenticating.current) return;
  isAuthenticating.current = true;
  try {
    const result = await signInWithPopup(auth, provider);
    await finalizeLogin(result);
  } finally {
    isAuthenticating.current = false;
  }
}
```
