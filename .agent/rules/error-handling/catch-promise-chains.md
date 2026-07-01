---
name: catch-promise-chains
paths: ["**/*.{ts,tsx}"]
---
# Add .catch() to Every Promise Chain

`handleSwitch().then(() => refetch())` with no `.catch()` creates unhandled
rejections. In React event handlers, use `void asyncFn()` or declare the
handler as `() => void | Promise<void>`. Every `.then()` chain needs a
`.catch()`.

## Verify

"Does every Promise chain have error handling? Are there fire-and-forget
async calls without .catch()?"

## Patterns

Bad — unhandled rejection if either promise rejects:

```typescript
onClick={() => handleSwitch().then(() => refetch())}
```

Good — errors are handled:

```typescript
onClick={() => {
  handleSwitch()
    .then(() => refetch())
    .catch(error => showErrorToast(error.message));
}}
```

For fire-and-forget where you genuinely don't care about errors:

```typescript
onClick={() => void handleSwitch()}
```
