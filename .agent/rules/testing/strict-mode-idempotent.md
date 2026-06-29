---
name: strict-mode-idempotent
paths: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}"]
---
# Test Auth Flows Under React StrictMode

React 18+ StrictMode double-invokes effects. Auth flows must be idempotent:
`signInWithCustomToken` should fire only once despite double-mount. Use
realistic mock delays in tests to catch timing bugs that pass with instant
mocks.

## Verify

"Does this auth flow work correctly under StrictMode double-invoke? Is the
test running with realistic async delays?"

## Patterns

Bad — test uses instant mock, misses double-mount bug:

```typescript
vi.mock('firebase/auth', () => ({
  signInWithCustomToken: vi.fn().mockResolvedValue({ user: mockUser }),
}));

test('login', () => {
  render(<App />); // Double-mount calls signIn twice, but instant mock hides it
});
```

Good — realistic delay exposes timing bugs:

```typescript
signInWithCustomToken.mockImplementation(
  () => new Promise(resolve => setTimeout(() => resolve({ user: mockUser }), 100))
);

test('login fires once under StrictMode', async () => {
  render(<StrictMode><App /></StrictMode>);
  await waitFor(() => expect(signInWithCustomToken).toHaveBeenCalledTimes(1));
});
```
