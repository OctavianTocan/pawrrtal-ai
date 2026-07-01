---
name: result-types
paths: ["**/*.{ts,tsx}"]
---
# Result Types for Expected Failures

For operations with expected failure modes (validation, network, parsing),
return a typed result object instead of throwing. Reserve exceptions for truly
unexpected situations. The compiler enforces handling both branches, and callers
can't accidentally forget try/catch.

## Verify

"Is this failure mode expected (network, validation, auth)? Should I use a
Result type instead of throwing?"

## Patterns

Bad — caller might not catch:

```typescript
async function getUser(id: string): Promise<User> {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

Good — error handling is explicit and compiler-enforced:

```typescript
type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

async function getUser(id: string): Promise<Result<User>> {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) return { ok: false, error: new Error(`HTTP ${res.status}`) };
  return { ok: true, value: await res.json() };
}
// Caller must handle both: if (!result.ok) { /* handle */ }
```
