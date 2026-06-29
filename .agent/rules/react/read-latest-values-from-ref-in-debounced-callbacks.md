---
name: read-latest-values-from-ref-in-debounced-callbacks
paths: ["**/*.{ts,tsx}"]
---
# Read Current Values from Refs Inside Debounced Callbacks, Not Stale Closures

When debouncing a save or API call, don't pass the current value as an
argument — it captures the value at call time, not execution time. Read from
a ref inside the debounced callback instead. This prevents oscillation bugs
where rapid changes cause the debounce to fire with outdated values.

## Verify

"Does my debounced callback use a captured argument or read from a ref?
Could rapid calls replay stale values?"

## Patterns

Bad — each keystroke captures value at call time:

```typescript
const debouncedSave = useMemo(
  () => debounce((title: string) => api.save(title), 2000),
  []
);
onChange={(e) => { setTitle(e.target.value); debouncedSave(e.target.value); }}
```

Good — reads current value at execution time:

```typescript
const titleRef = useRef(title);
useEffect(() => { titleRef.current = title; }, [title]);

const debouncedSave = useMemo(
  () => debounce(() => api.save(titleRef.current), 2000),
  []
);
onChange={(e) => { setTitle(e.target.value); debouncedSave(); }}
```
