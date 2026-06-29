---
name: validate-response-shape-at-boundary
paths: ["**/*.{ts,tsx,js,jsx}"]
---
# Validate API Response Shapes at the Boundary

Parse and validate API response shapes in the fetch wrapper — the boundary between your app and the outside world — not deep inside components. When validation happens in components, a malformed response passes through multiple layers before crashing, making the error hard to trace. Worse, different components might handle the same malformed data differently.

A single validation point at the API boundary means: (1) every consumer gets pre-validated data, (2) malformed responses fail fast with a clear error including the URL and response body, and (3) TypeScript types are actually trustworthy instead of being lies about what the API returned.

Use Zod, valibot, or a similar runtime schema validator. The validation cost is negligible compared to the network request, and it turns "Cannot read property 'name' of undefined" deep in a component into "API response validation failed for GET /api/users: expected array, got object" at the boundary.

## Verify

"Is API response validation happening at the fetch boundary, or are components assuming the shape is correct?"

## Patterns

Bad — components trust the response shape blindly:

```typescript
// api.ts
export async function getUsers(): Promise<User[]> {
 const res = await fetch("/api/users");
 return res.json(); // No validation — caller trusts this is User[]
}

// UserList.tsx
const users = await getUsers();
// 💥 Crashes if API returns { data: [...] } instead of [...]
users.map((u) => u.name);
```

Bad — validation scattered across components:

```typescript
// UserList.tsx
const data = await getUsers();
if (Array.isArray(data)) {
 data.map((u) => u.name);
}

// UserProfile.tsx
const data = await getUsers();
// Different component, different assumption about shape
const users = data?.users ?? data ?? [];
```

Good — validate at the boundary with a schema:

```typescript
import { z } from "zod";

const UserSchema = z.object({
 id: z.string(),
 name: z.string(),
 email: z.string().email(),
});

const UsersResponseSchema = z.array(UserSchema);

export async function getUsers(): Promise<User[]> {
 const res = await fetch("/api/users");
 if (!res.ok) {
  throw new ApiError(res.status, await res.text());
 }
 const json = await res.json();
 return UsersResponseSchema.parse(json);
 // ✅ Fails fast: "Expected array, received object" at the boundary
}

// All consumers get validated, typed data
```
