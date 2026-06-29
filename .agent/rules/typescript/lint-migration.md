---
name: lint-migration
paths: ["**/*.{ts,tsx}"]
---
# Use Current Linter Directives

When a project migrates linters (e.g., ESLint to Biome), update suppression
comments to match. Stale directives are dead code that confuses future readers
and may not suppress anything.

## Verify

"Are there any eslint-disable or eslint-disable-next-line comments in a
project that uses Biome? Should they be biome-ignore instead?"

## Patterns

Bad:

```ts
// eslint-disable-next-line react-hooks/exhaustive-deps
```

Good:

```ts
// biome-ignore lint/correctness/useExhaustiveDependencies: <reason>
```
