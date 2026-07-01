---
name: stopping-state-for-async-teardown
paths: ["**/*.ts", "**/*.tsx"]
---

# Add a Stopping State Between Active and Idle to Prevent Double-Resource Creation During Async Teardown

## Rule

State machines with async teardown need an explicit "stopping" state between "active" and "idle". Without it, users can tap start during the 2-5 second teardown window and create duplicate resources.

## Why

Recording, streaming, and other long-lived operations take time to clean up (encoding, flushing buffers, closing connections). During this window, the UI shows "stopped" but the system isn't ready for a new start. Double-tapping creates parallel operations that conflict.

## Good

```typescript
type RecordingState =
  | { status: 'idle' }
  | { status: 'recording'; startedAt: number }
  | { status: 'stopping'; stoppingAt: number }  // <-- this
  | { status: 'error'; error: Error };
```

## Verify

"Did I add an explicit `stopping` state between `active` and `idle`? Can users trigger a new operation during the teardown window? Could a double-start create conflicting resources?"

## Patterns

Good — state machine with stopping state:

```typescript
type RecordingState =
  | { status: 'idle' }
  | { status: 'recording'; startedAt: number }
  | { status: 'stopping'; stoppingAt: number }  // <-- this
  | { status: 'error'; error: Error };
```

Bad — direct idle → recording transition allows double-start:

```typescript
type BadState =
  | { status: 'idle' }
  | { status: 'recording'; startedAt: number };
// Problem: no guard between 'idle' and 'recording'
```

## Origin

a prior mobile project — double-tap during encoding gap started two recording sessions that fought over the microphone.
