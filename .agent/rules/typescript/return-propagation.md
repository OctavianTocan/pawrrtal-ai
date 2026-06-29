---
name: return-propagation
paths: ["**/*.{ts,tsx}"]
---
# Return Value Propagation

When a function wraps another function's call, propagate the return value
if the caller uses it for control flow. Dropping a return value silently
breaks signal chains between components.

## Verify

"Does every wrapper function explicitly return its inner call's result?
Are there code paths where a meaningful return value is silently dropped?"

## Patterns

Bad:

```ts
const onSend = useCallback((payload) => {
  handleSendRef.current(payload);
}, []);
```

Good:

```ts
const onSend = useCallback((payload) => {
  return handleSendRef.current(payload);
}, []);
```
