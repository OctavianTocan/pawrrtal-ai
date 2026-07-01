---
name: request-id-cancellation
paths: ["**/*.{ts,tsx}"]
---
# Request IDs to Cancel Stale Async Results

When async operations can be triggered in rapid succession (search-as-you-type,
pagination, filter changes), increment a request ID counter before each call
and check it still matches when the response arrives. Simpler than managing
AbortControllers and catches all stale result bugs.

## Verify

"Can this async operation be triggered again before the previous one completes?
Do I guard against stale results?"

## Patterns

Bad — slow response from earlier request overwrites newer results:

```typescript
async function onSearch(query: string) {
  const results = await api.search(query);
  setResults(results); // Stale if query changed during fetch
}
```

Good — stale responses are discarded:

```typescript
const requestIdRef = useRef(0);

async function onSearch(query: string) {
  const thisRequest = ++requestIdRef.current;
  const results = await api.search(query);
  if (thisRequest !== requestIdRef.current) return;
  setResults(results);
}
```
