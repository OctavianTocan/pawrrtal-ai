---
name: literal-unions
paths: ["**/*.{ts,tsx}"]
---
# Literal Union Types for Constrained Fields

If a field only accepts a known set of strings, type it as a literal union,
not bare `string`. This catches invalid values at compile time and provides
autocomplete. Use `Exclude<Union, Member>` to derive subtypes without
duplicating the list.

## Verify

"Does this field have a finite set of valid values typed as bare `string`?
Should it be a literal union?"

## Patterns

Bad — bare string accepts any value:

```typescript
interface Column {
  type: string;  // "string" | "number" | "date" but also "banana"
}
```

Good — literal union catches invalid values at compile time:

```typescript
type ColumnType = 'string' | 'number' | 'date' | 'boolean';
interface Column {
  type: ColumnType;
}
// Derive subtypes without duplication:
type PrimitiveColumnType = Exclude<ColumnType, 'date'>;
```
