---
name: buffer-high-frequency-stream-updates
paths: ["**/*.{ts,tsx,js,jsx}"]
---

# Buffer and Batch High-Frequency Stream Updates to Prevent UI Freezes

SSE and WebSocket consumers must handle backpressure. Buffer incoming messages and batch UI updates to prevent the rendering pipeline from choking.

When consuming a stream:

1. Buffer incoming messages in a ref (not state)
2. Flush to state on `requestAnimationFrame` or a 500ms timer
3. Cancel the flush callback in every exit path (unmount, error, stream end)
4. If the buffer exceeds a threshold, drop oldest messages or pause consumption

## Verify

"Am I calling setState on every stream message? Does this stream emit faster than React can render?"

## Patterns

Bad — setState on every message chokes the renderer:

```typescript
source.onmessage = (e) => setMessages(prev => [...prev, e.data]);
```

Good — buffer in a ref, flush on requestAnimationFrame:

```typescript
const buffer = useRef<string[]>([]);
const raf = useRef<number>();

source.onmessage = (e) => {
  buffer.current.push(e.data);
  if (!raf.current) {
    raf.current = requestAnimationFrame(() => {
      setMessages(prev => [...prev, ...buffer.current]);
      buffer.current = [];
      raf.current = undefined;
    });
  }
};

return () => {
  if (raf.current) cancelAnimationFrame(raf.current);
};
```

Note: A high-frequency stream (transcription tokens, chat messages) can emit faster than React can render. Without backpressure handling, the UI freezes, memory grows unbounded, and the app eventually crashes.
