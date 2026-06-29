---
name: usememo-and-reducers-must-be-pure
paths: ["**/*.{ts,tsx}"]
---
# useMemo Callbacks and Reducer Functions Must Be Pure - No Side Effects, No External Mutation

Functions declared as pure (useMemo callbacks, reducers, render bodies) must
not have side effects. Mutating refs, calling APIs, or writing to external
state inside a pure function violates the contract and causes subtle bugs.

## Verify

"Are there any side effects (ref mutations, API calls, state writes)
inside useMemo, useReducer, or render function bodies?"

## Patterns

Bad:

```ts
const value = useMemo(() => {
  myRef.current = computeExpensive(data);
  return myRef.current;
}, [data]);
```

Good:

```ts
const value = useMemo(() => computeExpensive(data), [data]);
// Assign ref in the render body or an effect, not inside useMemo
```
