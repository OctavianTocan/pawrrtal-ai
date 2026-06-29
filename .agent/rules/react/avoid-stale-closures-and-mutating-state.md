---
name: avoid-stale-closures-and-mutating-state
paths: ["**/*.{ts,tsx}"]
---
# Avoid Stale Closures and Direct State Mutation in React Components

Three rules that prevent the most common React state bugs:

**1. Functional setState when updating based on current state.**
Prevents stale closures and makes callbacks stable (no state dependency).

**2. Immutable array methods** — use `toSorted()`, `toReversed()`,
`toSpliced()`, `.with()` instead of `sort()`, `reverse()`, `splice()`.
Mutating arrays breaks React's immutability model.

**3. Lazy state initialization** — pass a function to `useState` for
expensive initial values. Without it, the initializer runs every render.

## Verify

"Are there setState calls that reference state directly instead of using
the functional form? Are there .sort()/.reverse()/.splice() calls on
props or state? Are there expensive useState initializers without the
function form?"

## Patterns

Bad — stale closure, unstable callback:

```tsx
const addItem = useCallback((item: Item) => {
  setItems([...items, item]);
}, [items]); // recreated every time items changes
```

Good — functional update, stable callback:

```tsx
const addItem = useCallback((item: Item) => {
  setItems((curr) => [...curr, item]);
}, []); // stable, no stale closure risk
```

Bad — mutates props array:

```tsx
const sorted = useMemo(() => users.sort((a, b) => a.name.localeCompare(b.name)), [users]);
```

Good — immutable sort:

```tsx
const sorted = useMemo(() => users.toSorted((a, b) => a.name.localeCompare(b.name)), [users]);
```

Bad — expensive initializer runs every render:

```tsx
const [index, setIndex] = useState(buildSearchIndex(items));
```

Good — lazy initialization runs only once:

```tsx
const [index, setIndex] = useState(() => buildSearchIndex(items));
```
