---
name: validate-boundaries
paths: ["**/*.{ts,tsx}"]
---
# Validate External Data at Trust Boundaries

TypeScript types are compile-time only. Any data crossing a trust boundary
(API responses, localStorage, URL params, form data) must be validated at
runtime with a schema library like Zod. Derive types from schemas with
`z.infer<typeof Schema>` so the type and validation stay in sync.

## Verify

"Am I using `as Type` or raw `JSON.parse` on data from outside my process?
Should I add a runtime schema at this boundary?"

## Patterns

Bad — trusts the shape of external data:

```typescript
const data = await fetch('/api/user').then(r => r.json()) as User;
const stored = JSON.parse(localStorage.getItem('prefs')!) as Preferences;
```

Good — validates at the boundary, derives types from the schema:

```typescript
const UserSchema = z.object({ name: z.string(), email: z.string().email() });
type User = z.infer<typeof UserSchema>;

const data = UserSchema.parse(await fetch('/api/user').then(r => r.json()));
```
