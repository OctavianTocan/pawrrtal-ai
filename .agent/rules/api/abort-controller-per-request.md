---
name: abort-controller-per-request
paths: ["**/*.{ts,tsx,js,jsx}"]
---
# Create a New AbortController Per Request

A common mistake is creating one `AbortController` and reusing it across multiple requests. When you call `controller.abort()`, it cancels **every** request using that controller's signal — not just the one you intended to cancel. Once aborted, the controller's signal stays in the aborted state permanently and cannot be reset.

This manifests as "all my API calls fail after cancelling one" — especially in React effects where a cleanup function aborts on unmount, accidentally killing requests from sibling components sharing the same controller.

Create a new `AbortController` for each request (or each logical group of requests that should be cancelled together). Store it in a ref if you need to cancel from a different scope.

## Verify

"Is this AbortController shared across independent requests? Will aborting one request accidentally cancel others?"

## Patterns

Bad — shared controller cancels all requests:

```typescript
const controller = new AbortController();

async function fetchUser(id: string) {
 return fetch(`/api/users/${id}`, { signal: controller.signal });
}

async function fetchPosts(userId: string) {
 return fetch(`/api/posts?user=${userId}`, { signal: controller.signal });
}

// Cancelling user fetch also cancels posts fetch
controller.abort();
```

Bad — reusing aborted controller:

```typescript
const controller = new AbortController();

// First request — works fine
await fetch("/api/data", { signal: controller.signal });

// Cancel it
controller.abort();

// Second request — fails immediately because signal is already aborted
await fetch("/api/other", { signal: controller.signal });
// ❌ AbortError: The operation was aborted
```

Good — new controller per request:

```typescript
function fetchWithCancel(url: string) {
 const controller = new AbortController();
 const promise = fetch(url, { signal: controller.signal });
 return { promise, cancel: () => controller.abort() };
}

const user = fetchWithCancel(`/api/users/${id}`);
const posts = fetchWithCancel(`/api/posts?user=${id}`);

// Cancel only the user request
user.cancel();
// Posts request continues unaffected
```

Good — per-request controller in React effects:

```typescript
useEffect(() => {
 const controller = new AbortController();
 fetch(`/api/users/${id}`, { signal: controller.signal })
  .then((res) => res.json())
  .then(setUser)
  .catch((e) => {
   if (e.name !== "AbortError") throw e;
  });
 return () => controller.abort();
}, [id]);
```
