---
name: trace-props-through-refactor
paths: ["**/*.{ts,tsx}"]
---
# Trace All Props Through Refactor Boundaries

When splitting a component (e.g., View/Container split), trace every prop
in the new interface to verify it is actually consumed in the component
body. Props that were used in the original component may become orphaned
when the logic moves to the container and the view only renders.

## Verify

"After a component split, does every prop in the View's interface get
used in the View's JSX or logic? Are there any props being passed through
that nothing consumes?"

## Patterns

Bad -- ariaLabel passed through but never used in View:

```tsx
interface FooViewProps {
  ariaLabel: string;  // passed from container
  label: string;
}
function FooView({ ariaLabel, label }: FooViewProps) {
  return <div>{label}</div>; // ariaLabel unused -- Biome catches this
}
```

Good -- either use it or remove it:

```tsx
interface FooViewProps {
  label: string;
}
function FooView({ label }: FooViewProps) {
  return <div>{label}</div>;
}
```
