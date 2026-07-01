---
name: factory-over-shared-mutable
paths: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}"]
---
# Factory Functions for Test Data

Module-level mutable objects mutated via `Object.assign` in tests create
hidden coupling between test cases. If `beforeEach` doesn't clean up properly,
state leaks between tests. Use factory functions that return fresh objects.

## Verify

"Am I mutating a shared object in tests? Should I use a factory that returns
a fresh copy?"

## Patterns

Bad — shared mutable state leaks between tests:

```typescript
const mockSubscription = { plan: 'free', active: true };

beforeEach(() => {
  Object.assign(mockSubscription, { plan: 'free', active: true });
});

test('upgrade', () => {
  mockSubscription.plan = 'pro'; // Leaks if afterEach is missing
});
```

Good — factory returns fresh data every time:

```typescript
function createMockSubscription(overrides?: Partial<Subscription>) {
  return { plan: 'free', active: true, ...overrides };
}

test('upgrade', () => {
  const sub = createMockSubscription({ plan: 'pro' });
});
```
