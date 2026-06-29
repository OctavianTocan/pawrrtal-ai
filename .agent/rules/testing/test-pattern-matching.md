---
name: test-pattern-matching
paths: ["**/*.test.{ts,tsx}", "**/__tests__/**"]
---
# Match Test Patterns to Code Patterns

Use renderHook for React hooks. Use direct function calls for plain factory
functions. Using the wrong test utility creates unnecessary complexity and
misleading test structure.

## Verify

"Are there tests using renderHook/act for functions that aren't hooks?
Are there tests calling hooks directly without renderHook?"

## Patterns

Bad:

```ts
// createGoogleLogin is a factory, not a hook
const { result } = renderHook(() => createGoogleLogin(ref));
act(() => { result.current.login(); });
```

Good:

```ts
const login = createGoogleLogin(ref);
login.login();
```
