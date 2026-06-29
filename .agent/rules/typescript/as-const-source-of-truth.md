---
name: as-const-source-of-truth
paths: ["**/*.{ts,tsx}"]
---
# as const: Single Source of Truth for Unions

When an object holds a fixed set of values (routes, config keys, enum-like
maps), declare it with `as const` and derive union types from it. Never
manually define a union that duplicates values already in an object.
`as const` gives deep readonly + literal types. Use `keyof typeof obj`
for key unions and `(typeof obj)[keyof typeof obj]` for value unions.

## Verify

"Are there manually defined union types that duplicate values already in a
const object? Could they be derived with typeof + keyof instead?"

## Patterns

Bad — manual union duplicates the object values:

```ts
const routes = { home: '/', admin: '/admin', users: '/users' };
type Route = '/' | '/admin' | '/users'; // duplicated, drifts
```

Good — derive the union from the object:

```ts
const routes = { home: '/', admin: '/admin', users: '/users' } as const;
type Route = (typeof routes)[keyof typeof routes]; // '/' | '/admin' | '/users'
```

Bad — Object.freeze (shallow, no deep literal types):

```ts
const config = Object.freeze({ api: { url: '/api' } });
config.api.url = '/other'; // no error — freeze is shallow
```

Good — as const (deep readonly + deep literal types):

```ts
const config = { api: { url: '/api' } } as const;
config.api.url = '/other'; // Error: readonly
```

Good — key union derived from as const:

```ts
const routes = { home: '/', admin: '/admin' } as const;
type RouteKey = keyof typeof routes; // 'home' | 'admin'
function goToRoute(key: RouteKey) { navigate(routes[key]); }
```
