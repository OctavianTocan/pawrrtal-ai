---
name: storage-try-catch
paths: ["**/*.{ts,tsx}"]
---
# Wrap Storage Access in try-catch

In private browsing or when storage is full, `sessionStorage.setItem()` and
`localStorage.setItem()` throw. Always wrap storage access in try-catch to
prevent crashes. Return a fallback value on read failures.

## Verify

"Will this storage access crash in private browsing or when storage is full?"

## Patterns

Bad — crashes in Safari private browsing:

```typescript
sessionStorage.setItem('redirect', window.location.href);
const saved = JSON.parse(localStorage.getItem('prefs')!);
```

Good — graceful fallback:

```typescript
try {
  sessionStorage.setItem('redirect', window.location.href);
} catch {
  // Private browsing or storage full — proceed without saving
}

function getStoredPrefs(): Preferences {
  try {
    const raw = localStorage.getItem('prefs');
    return raw ? JSON.parse(raw) : defaultPrefs;
  } catch {
    return defaultPrefs;
  }
}
```
