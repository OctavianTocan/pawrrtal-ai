---
name: derive-types
paths: ["**/*.{ts,tsx}"]
---
# Derive Types, Don't Duplicate

Never manually redefine a subset of an existing type. Use utility types to
derive from a single base type so changes propagate automatically. Key
patterns: `Pick<T, K>` for specific properties, `Omit<T, K>` to exclude
properties, `Partial<T>` for update functions, `Record<Union, V>` for
objects with required keys, `Awaited<ReturnType<typeof fn>>` for async
return types.

## Verify

"Are there manually defined types that duplicate a subset of an existing
type? Could they use Pick, Omit, Partial, or Record to derive from the
base type instead?"

## Patterns

Bad — manual subset that drifts when User changes:

```ts
function renderUserDetails(user: { name: string; age: number }) { ... }
```

Good — derived from User, auto-updates:

```ts
function renderUserDetails(user: Pick<User, 'name' | 'age'>) { ... }
```

Bad — manually omitting a field:

```ts
function createUser(user: { name: string; age: number; address: Address }) { ... }
```

Good — derived via Omit:

```ts
function createUser(user: Omit<User, 'id'>) { ... }
```

Bad — manually making fields optional:

```ts
function updateUser(user: { name?: string; age?: number; id?: string }) { ... }
```

Good — derived via Partial:

```ts
function updateUser(user: Partial<User>) { ... }
```

Bad — manually typing an async function's return:

```ts
type UserData = { name: string; id: string };
```

Good — derived from the function:

```ts
type UserData = Awaited<ReturnType<typeof getUser>>;
```
