---
name: check-response-before-parse
paths: ["**/*.{ts,tsx}"]
---
# Check Response Status Before Parsing Body

A 401/500 response with a JSON body will be silently treated as valid data
if you parse with `res.json()` without checking `res.ok` first. Always check
the response status before parsing. For 401s with `auth: 'required'`, retry
once with a force-refreshed token.

## Verify

"Am I checking `res.ok` before calling `res.json()`? Could an error response
be silently treated as valid data?"

## Patterns

Bad — error response parsed as valid data:

```typescript
const data = await fetch('/api/subscription').then(r => r.json());
setSubscription(data); // data might be { error: "Unauthorized" }
```

Good — status checked first:

```typescript
const res = await fetch('/api/subscription');
if (!res.ok) {
  if (res.status === 401) return await retryWithFreshToken();
  throw new ApiError(res.status, await res.text());
}
const data = await res.json();
```
