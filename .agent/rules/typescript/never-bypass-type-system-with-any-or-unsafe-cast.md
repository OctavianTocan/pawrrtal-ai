---
name: never-bypass-type-system-with-any-or-unsafe-cast
paths: ["**/*.{ts,tsx}"]
---
# Never Bypass the Type System with any, as unknown as X, or @ts-ignore - Fix the Types

Use `import type` for type-only imports. Use proper null checks or optional
chaining instead of non-null assertion (`!`). Use type guards for complex
narrowing. These patterns prevent runtime errors the type system should catch.

## Verify

"Are there non-null assertions (!) that should be proper null checks?
Are there value imports that should be import type?"

## Patterns

Bad:

```ts
import { MyType } from './types';
const value = someNullable!.property;
```

Good:

```ts
import type { MyType } from './types';
if (someNullable) {
  const value = someNullable.property;
}
```
