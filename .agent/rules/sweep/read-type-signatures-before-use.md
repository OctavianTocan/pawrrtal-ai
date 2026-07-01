---
name: read-type-signatures-before-use
paths: ["**/*.{ts,tsx}"]
---
# Read Type Signatures Before Using Components or APIs

Before passing data to a component, wrapping output in a component, or
calling an API, read the target's type signature first. Do not assume
a component accepts `ReactNode` children, that extending `ComponentProps`
won't conflict with your custom props, or that an API endpoint accepts
your input shape.

## Verify

"Am I about to use a component or API? Did I read its type signature /
prop interface / API contract first? Could any of my props collide with
inherited types?"

## Checks

1. **Before wrapping content in a component**: read the component's
   `children` type. If it accepts `string`, do not pass `ReactNode`.
2. **Before extending `ComponentProps<'element'>`**: check which event
   handlers the element type includes (onSubmit, onChange, onClick, etc.).
   Use `Omit<>` to exclude any that clash with your custom props.
3. **Before calling an API with dynamic IDs**: verify the IDs are valid
   for that API path (e.g., PENDING review threads are not resolvable
   via GraphQL mutation).

## Patterns

Bad -- assumes Calligraph accepts ReactNode:

```tsx
<Calligraph>{highlightMatch(text, query)}</Calligraph>
// TypeError: Calligraph children must be string
```

Good -- checks type first, conditionally wraps:

```tsx
// Calligraph accepts string children only
const content = highlightMatch(text, query);
return typeof content === 'string'
  ? <Calligraph>{content}</Calligraph>
  : content;
```

Bad -- extends div props without checking for conflicts:

```tsx
interface Props extends React.ComponentProps<'div'> {
  onSubmit: (e: FormEvent<HTMLFormElement>) => void; // clashes with div's onSubmit
}
```

Good -- omits the conflicting inherited prop:

```tsx
interface Props extends Omit<React.ComponentProps<'div'>, 'onSubmit'> {
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
}
```
