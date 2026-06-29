---
name: discriminated-unions
paths: ["**/*.{ts,tsx}"]
---
# Discriminated Unions Over Boolean Flags

When a component or store uses 2+ boolean flags to represent mutually exclusive
states, replace them with a single discriminated union. This makes impossible
states unrepresentable at the type level and eliminates entire categories of
bugs where flags get out of sync.

## Verify

"Am I using 2+ boolean flags that represent mutually exclusive states? Could I
replace them with a discriminated union?"

## Patterns

Bad — multiple booleans allow impossible combinations:

```typescript
interface RequestState {
  isLoading?: boolean;
  isError?: boolean;
  isSuccess?: boolean;
  data?: Data;
  error?: Error;
}
// Nothing prevents { isLoading: true, isError: true, data: staleData }
```

Good — impossible states are unrepresentable:

```typescript
type RequestState =
  | { type: 'idle' }
  | { type: 'loading' }
  | { type: 'success'; data: Data }
  | { type: 'error'; error: Error };
```

For operations with a non-trivial teardown (encoding, saving, uploading), include
a `stopping` transition state to prevent double-invocation:

```typescript
type RecordingState =
  | { type: 'idle' }
  | { type: 'recording'; sessionId: string }
  | { type: 'stopping'; sessionId: string }  // 2-5s encoding gap
  | { type: 'error'; error: Error };
```
