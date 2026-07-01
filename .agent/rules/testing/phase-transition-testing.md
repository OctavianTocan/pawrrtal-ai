---
name: phase-transition-testing
paths: ["**/*.test.ts", "**/*.test.tsx", "**/*.spec.ts", "**/*.spec.tsx"]
---

# Test Every State Machine Phase Transition Independently, Not Just End States

When testing state machines, every phase transition must have tests for:

1. Happy path (valid transition succeeds)
2. Error path (invalid input / failure mid-transition)
3. Rollback (system returns to previous state on failure)

Don't just test "start → end." Test each transition boundary independently.

**Why:** State machines with phase-aware streaming (e.g., agent responses that go Thinking → Content → Tool Use → Done) fail in subtle ways at transition boundaries. Testing only the final output misses cases where the machine gets stuck in an intermediate state.

## Verify

"Have I tested each transition boundary independently? Does each phase have a happy path test, an error path test, and a rollback test? Could the machine get stuck in an intermediate state?"

## Patterns

Test each transition explicitly:

```typescript
describe('RecordingState transitions', () => {
  test('idle → recording succeeds', () => {});
  test('recording → stopping succeeds', () => {});
  test('stopping → idle succeeds', () => {});
  test('recording → error on device failure', () => {});
  test('stopping → error on flush failure', () => {});
  test('error → idle resets cleanly', () => {});
});
```

Don't just test end-to-end:

```typescript
// Bad — misses intermediate state bugs
test('start recording and stop', () => {
  // This passes but machine may get stuck in 'stopping'
});

// Good — tests each boundary
test('stopping → idle after flush completes', () => {});
```

**Learned from:** tap (OctavianTocan/tap) — phase-aware streaming pipeline testing.
