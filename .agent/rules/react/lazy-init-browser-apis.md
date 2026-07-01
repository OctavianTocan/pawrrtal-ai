---
name: lazy-init-browser-apis
paths: ["**/*.{ts,tsx,js,jsx}"]
---

# Lazy-Initialize Browser APIs on First Use

APIs like `AudioContext`, `MediaRecorder`, `IntersectionObserver`, and
`localStorage` should be initialized lazily on first access, not at module
scope or component mount. Module-scope initialization crashes in SSR,
service workers, and test environments.

## Verify

"Am I initializing a browser API at module scope? Should I lazy-init on
first use?"

## Patterns

Bad — crashes in SSR, service workers, tests:

```typescript
const audioContext = new AudioContext();
export function getAnalyser() {
  return audioContext.createAnalyser();
}
```

Good — lazy init with null check:

```typescript
let audioContext: AudioContext | null = null;
export function getAudioContext(): AudioContext | null {
  if (!audioContext && typeof window !== 'undefined') {
    audioContext = new AudioContext();
  }
  return audioContext;
}
```
