---
name: release-stream-locks
paths: ["**/*.{ts,tsx}"]
---
# Release Stream Locks in Finally Blocks

When reading from a ReadableStream (SSE, fetch streaming), always call
`reader.releaseLock()` in a `finally` block. Wrap the release in a try-catch
since it throws if the stream is already errored. Process any remaining
buffered data before releasing.

## Verify

"Am I releasing the stream reader lock in a finally block? Could an error
leave the lock held?"

## Patterns

Bad — lock leaks on error, prevents subsequent reads:

```typescript
const reader = response.body!.getReader();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  processChunk(value);
}
```

Good — lock always released, buffer flushed:

```typescript
const reader = response.body!.getReader();
try {
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    processChunk(value);
  }
  processRemainingBuffer();
} finally {
  try { reader.releaseLock(); } catch { /* stream already errored */ }
}
```
