---
name: wrapper-functions-must-match-inner-param-types
paths: ["**/*.{ts,tsx}"]
---
# Wrapper Functions Must Accept All Parameters of the Function They Wrap - No Silent Dropping

When a function wraps another function and forwards parameters, derive the
parameter types from the inner function using `Parameters<typeof fn>`.
This ensures the wrapper stays in sync when the inner function's signature
changes. Manually duplicating parameter types creates silent drift.

## Verify

"Are there wrapper functions with parameter types manually duplicated from
the inner function? Could they use Parameters<typeof fn>[N] instead?"

## Patterns

Bad — manually duplicated parameter type drifts:

```ts
function getUser(id: string) { ... }
function getUserWrapper(id: string, useCache: boolean) {
  return getUser(id);
}
```

Good — derived from inner function, auto-updates:

```ts
function getUser(id: string) { ... }
function getUserWrapper(id: Parameters<typeof getUser>[0], useCache: boolean) {
  return getUser(id);
}
```

Good — spreading all params when fully forwarding:

```ts
function getUser(id: string, options: RequestOptions) { ... }
function getUserWrapper(...args: Parameters<typeof getUser>) {
  return getUser(...args);
}
```
