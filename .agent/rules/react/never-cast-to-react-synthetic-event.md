---
name: never-cast-to-react-synthetic-event
paths: ["**/*.ts", "**/*.tsx"]
---

# Never Cast Plain Objects to React Synthetic Event Types - They Lack preventDefault/stopPropagation

## Rule

Never cast plain objects to React synthetic event types. If a component needs a value rather than an event, change the callback signature to accept the value directly.

## Why

Casting `{ target: { value: 'foo' } } as React.ChangeEvent<HTMLInputElement>` launders the shape. The cast satisfies TypeScript but the object lacks `preventDefault()`, `stopPropagation()`, and other event methods. Any code path that calls those methods crashes at runtime.

## Bad

```typescript
onChange({ target: { value: newValue } } as React.ChangeEvent<HTMLInputElement>);
```

## Good

```typescript
// Change the prop type to accept the value directly
onValueChange(newValue: string): void;
```

## Origin

a prior webapp — faked ChangeEvent casts caused runtime crashes when error boundaries called preventDefault() on the fake event.

## Verify

"Is any code casting a plain object `as React.ChangeEvent` (or any synthetic event type)? Does the consumer only need the value? Can the callback be changed to accept the value directly?"

## Patterns

Bad — fake event cast satisfies TypeScript but crashes at runtime:

```typescript
interface Props {
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

function Wrapper({ onChange }: Props) {
  const handleChange = (value: string) => {
    // Cast launders the shape — no preventDefault, no stopPropagation
    onChange({ target: { value } } as React.ChangeEvent<HTMLInputElement>);
  };

  return <CustomInput onValueChange={handleChange} />;
}

// Somewhere downstream — CRASH:
// onChange handler calls e.preventDefault() → e.preventDefault is not a function
```

Good — accept the value directly, no cast needed:

```typescript
interface Props {
  onValueChange: (value: string) => void;
}

function Wrapper({ onValueChange }: Props) {
  return <CustomInput onValueChange={onValueChange} />;
}
```
