---
name: optimistic-ui-rollback
paths: ["**/*.{ts,tsx,js,jsx}"]
---

# Rollback at Every Failure Path in Optimistic UI

When updating UI optimistically before an async operation confirms, every
code path that can fail must explicitly roll back the UI state. A single
unguarded failure path creates "zombie" indicators: recording icon stuck on,
loading spinner forever, toggle in wrong position.

## Verify

"Does every failure path in this optimistic flow roll back the UI? Can any
code path leave the UI in an impossible state?"

## Patterns

Bad — state stuck on failure:

```typescript
async function startRecording() {
  setRecordingState('recording'); // Optimistic
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  // If getUserMedia fails, state stays 'recording' forever
  recorder = new MediaRecorder(stream);
  recorder.start();
}
```

Good — rollback on any failure:

```typescript
async function startRecording() {
  setRecordingState('recording');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    recorder.start();
  } catch (error) {
    setRecordingState('idle'); // Rollback
    throw error;
  }
}
```
