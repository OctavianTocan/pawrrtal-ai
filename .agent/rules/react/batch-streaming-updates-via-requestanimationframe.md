---
name: batch-streaming-updates-via-requestanimationframe
paths: ["**/*.{ts,tsx}"]
---
# Batch High-Frequency Streaming Updates via requestAnimationFrame, Not setState on Every Event

Server-Sent Events and WebSocket tokens often arrive every 10-20ms, but
screens refresh at 60fps (16.67ms). Instead of updating state on every token,
buffer tokens and flush once per `requestAnimationFrame` call. Cancel the RAF
callback in every exit path (abort, error, complete, unmount) to prevent leaks.

## Verify

"Am I updating React state on every streaming token? Should I batch via RAF?"

## Patterns

Bad — re-render on every token (~80/s):

```typescript
eventSource.onmessage = (e) => {
  setContent(prev => prev + e.data);
};
```

Good — buffer and flush at screen refresh rate:

```typescript
const bufferRef = useRef('');
const rafRef = useRef<number>();

eventSource.onmessage = (e) => {
  bufferRef.current += e.data;
  if (!rafRef.current) {
    rafRef.current = requestAnimationFrame(() => {
      setContent(prev => prev + bufferRef.current);
      bufferRef.current = '';
      rafRef.current = undefined;
    });
  }
};

// Cleanup — call this on abort, error, complete, AND unmount:
function cleanup() {
  if (rafRef.current) {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = undefined;
  }
  bufferRef.current = '';
}
```
