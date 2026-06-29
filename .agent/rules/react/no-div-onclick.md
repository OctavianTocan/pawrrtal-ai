---
name: no-div-onclick
paths: ["**/*.{ts,tsx}"]
---
# No div onClick — Use Semantic Elements

`<div onClick>` creates a click target invisible to assistive technology:
no keyboard focus, no role, no accessible name. Use `<button type="button">`
for actions and `<a href>` for navigation. Always include an explicit `type`
on buttons to prevent accidental form submission.

## Verify

"Am I using a div or span with an onClick? Should this be a button or anchor?"

## Patterns

Bad — inaccessible, not focusable, no keyboard activation:

```tsx
<div onClick={handleDelete} className="cursor-pointer text-red-500">
  Delete
</div>
```

Good — focusable, keyboard-accessible, announced by screen readers:

```tsx
<button type="button" onClick={handleDelete} className="text-red-500">
  Delete
</button>
```
