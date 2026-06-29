---
name: parallel-async
paths: ["**/*.{ts,tsx}"]
---
# Parallelize Independent Async Operations

When multiple async operations have no dependencies on each other, execute
them concurrently with `Promise.all()`. Sequential awaits create waterfall
chains that are 2-10x slower. This applies to API routes, data fetching,
server components, and any async function.

## Verify

"Are there sequential await calls that could run in parallel? Do the
operations actually depend on each other's results, or are they independent?"

## Patterns

Bad — sequential awaits (3 round trips):

```ts
const user = await fetchUser(id);
const posts = await fetchPosts(id);
const comments = await fetchComments(id);
```

Good — parallel execution (1 round trip):

```ts
const [user, posts, comments] = await Promise.all([
  fetchUser(id),
  fetchPosts(id),
  fetchComments(id),
]);
```

Bad — sequential where only the last depends on the first:

```ts
const user = await fetchUser(id);
const settings = await fetchSettings(id);
const recommendations = await getRecommendations(user);
```

Good — parallel the independent ones, then use result:

```ts
const [user, settings] = await Promise.all([
  fetchUser(id),
  fetchSettings(id),
]);
const recommendations = await getRecommendations(user);
```
