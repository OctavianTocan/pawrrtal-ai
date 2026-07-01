---
name: purity-in-memo-and-reducers
paths: ["**/*.ts", "**/*.tsx"]
---

# Purity in useMemo and Reducers

`useMemo` callbacks and reducer functions must be pure. No side effects, no external mutation, no API calls, no state dispatches. If you need a side effect, use `useEffect`.

**Why:** React may call useMemo/reducers multiple times (StrictMode, concurrent mode, re-renders). Side effects in these functions execute unpredictably, causing double API calls, double state updates, and race conditions that are extremely hard to debug.

**Learned from:** the vendored app — AGENTS.md convention.

## Verify

"Does any useMemo callback or reducer function dispatch state, call APIs, or mutate external variables? Should this side effect be in useEffect instead?"

## Patterns

Bad — side effect in useMemo fires unpredictably:

```typescript
const filteredItems = useMemo(() => {
  analytics.track('items_filtered', { count: items.length }); // side effect
  setFilterCount(items.length); // state dispatch in useMemo
  return items.filter(predicate);
}, [items, predicate]);
```

Bad — API call in a reducer:

```typescript
function reducer(state: State, action: Action): State {
  if (action.type === 'submit') {
    api.submit(action.payload); // side effect in reducer
    return { ...state, submitted: true };
  }
  return state;
}
```

Good — pure useMemo, side effect in useEffect:

```typescript
const filteredItems = useMemo(() => {
  return items.filter(predicate);
}, [items, predicate]);

useEffect(() => {
  analytics.track('items_filtered', { count: filteredItems.length });
  setFilterCount(filteredItems.length);
}, [filteredItems]);
```

Good — pure reducer, API call dispatched from effect:

```typescript
function reducer(state: State, action: Action): State {
  if (action.type === 'submit') {
    return { ...state, submitting: true };
  }
  if (action.type === 'submit_success') {
    return { ...state, submitting: false, submitted: true };
  }
  return state;
}

// API call in a thunk, saga, or useEffect — never in the reducer
```
