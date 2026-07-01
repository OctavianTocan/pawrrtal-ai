---
name: satisfies-vs-annotations
paths: ["**/*.{ts,tsx}"]
---
# satisfies vs Variable Annotations

`satisfies` validates a value matches a type WITHOUT widening — the inferred
type stays narrow (literal keys, literal values, exact shape). Use it for
config objects, route maps, and theme objects where you want autocomplete on
specific keys and preserved literal types. Combine with `as const` for
deeply readonly validated objects.

Variable annotations (`: Type`) WIDEN the type. Use them when you need to
add properties later or want the broader type (e.g., a `Record` you'll
assign new keys to after declaration).

## Verify

"Is there a `satisfies` on a value that gets mutated/extended after declaration?
Is there a variable annotation on a config/map object that loses autocomplete
or literal types unnecessarily?"

## Patterns

Bad — satisfies on a mutable object (can't add keys later):

```ts
const scores = { math: 100 } satisfies Record<string, number>;
scores.english = 95; // Error: property 'english' does not exist
```

Good — variable annotation when you need to widen:

```ts
const scores: Record<string, number> = { math: 100 };
scores.english = 95; // Works — type is wide
```

Bad — variable annotation on a config (loses narrowing):

```ts
const config: Record<string, string | number> = { wide: 'foo', narrow: 42 };
config.wide; // string | number — lost the specific types
```

Good — satisfies on a config (keeps narrowing):

```ts
const config = { wide: 'foo', narrow: 42 } satisfies Record<string, string | number>;
config.wide;   // string — autocomplete works, literal type preserved
config.narrow; // number — not string | number
```

Good — as const satisfies for readonly validated objects:

```ts
const routes = {
  '/': { component: 'Home' },
  '/about': { component: 'About' },
} as const satisfies Record<string, { component: string }>;
routes['/'].component; // 'Home' — literal, readonly, validated
```
