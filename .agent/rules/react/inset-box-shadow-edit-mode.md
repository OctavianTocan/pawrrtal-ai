---
name: inset-box-shadow-edit-mode
paths: ["**/*.ts", "**/*.tsx", "**/*.css"]
---

# Inset Box-Shadow for Edit Mode Outlines

Use `box-shadow: inset` for edit-mode outlines and selection indicators, not `border`. Border adds to the box model and shifts layout by 1-2px. Inset box-shadow renders on top of the element without layout shift.

**Why:** When elements snap 1-2px on edit mode toggle, it looks broken. The shift is especially visible in grids and aligned layouts. Inset box-shadow avoids this entirely.

**Learned from:** the vendored app — UI polish convention.

## Verify

"Does toggling edit mode shift elements by 1-2px? Am I using `border` for selection outlines? Could I replace it with `box-shadow: inset` to avoid layout shifts?"

## Patterns

Bad — border adds to box model, shifts layout:

```css
.editable-card {
  border: 1px solid transparent;
}
.editable-card.selected {
  border: 1px solid blue; /* adds 1px → element shifts right and down */
}
```

Good — inset box-shadow, no layout shift:

```css
.editable-card {
  box-shadow: none;
}
.editable-card.selected {
  box-shadow: inset 0 0 0 1px blue; /* renders on top, zero layout shift */
}
```
