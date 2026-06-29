---
name: tsdoc-on-every-exported-function
paths: ["**/*.ts", "**/*.tsx"]
---

# TSDoc Comments Required on Every Exported Function, Type, and Module

All code you write or modify must include proper documentation:

## TSDoc / JSDoc

Every exported function, class, interface, type alias, and constant must
have a TSDoc (TypeScript) or JSDoc (JavaScript) comment. Include:

- A concise summary of what it does / represents
- `@param` for each parameter (skip if self-evident from the name + type)
- `@returns` describing what the return value represents

Do not document private/internal helpers unless the logic is non-obvious.

## Inline Comments — Explain WHY, Not WHAT

Add inline comments when the code's _reason_ is not self-evident:

- Why a particular approach was chosen over simpler alternatives
- Why a value is hardcoded or a seemingly-redundant check exists
- Why an operation is ordered a specific way (timing, race conditions)
- Constraints or invariants that the surrounding code depends on

Do NOT add comments that restate what the code already says:

Bad:  `// Increment the counter`
Good: `// Rate-limit window resets every 60s — counter must reset with it`

## Verify

"Does every export have a TSDoc? Do inline comments explain WHY, not WHAT?
Did I add `@returns` to functions with non-obvious return values?"

## Patterns

Bad — no documentation on exports:

```typescript
export function calculateTotal(items: Item[]): number {
  return items.reduce((sum, item) => sum + item.price * item.quantity, 0);
}
// What does this return? Subtotal? With tax? With discount?
```

Good — TSDoc on every export, inline comments explain why:

```typescript
/**
 * Calculate the pre-tax subtotal for a list of order items.
 * @param items - The order line items to total
 * @returns The sum of (price × quantity) for all items, excluding tax and shipping
 */
export function calculateTotal(items: Item[]): number {
  // Exclude items with zero quantity — they're placeholders for backordered stock
  return items
    .filter((item) => item.quantity > 0)
    .reduce((sum, item) => sum + item.price * item.quantity, 0);
}
```
