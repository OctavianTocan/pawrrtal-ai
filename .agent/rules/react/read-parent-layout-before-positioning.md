---
name: read-parent-layout-before-positioning
paths: ["**/*.{ts,tsx,css}"]
---

# Measure Parent Dimensions Before Setting Absolute Position on Children

Before adding any positioning property (`translate`, `absolute`,
`left-1/2`, `relative` with offsets) to a child element, read the
parent's existing layout properties. If the parent already handles the
layout concern, don't add redundant positioning to the child.

## Verify

"Did I read the parent's display, align-items, justify-content, and
position before adding positioning to this child? Could the parent's
existing layout already handle what I'm trying to do?"

## Patterns

Bad — translate centering inside a flex-centered parent (double-offset):

```tsx
{/* Parent: flex flex-col items-center */}
<div className="relative left-1/2 -translate-x-1/2 flex items-center">
  {/* Shifted ~70px right from double-centering */}
```

Good — let parent center, add justify-center to the row:

```tsx
{/* Parent: flex flex-col items-center */}
<div className="flex items-center justify-center">
  {/* Properly centered */}
```

Bad — absolute positioning when flex gap would work:

```tsx
<div className="relative">
  <span className="absolute right-0 top-1/2 -translate-y-1/2">icon</span>
```

Good — flex with gap:

```tsx
<div className="flex items-center gap-2">
  <span>icon</span>
```
