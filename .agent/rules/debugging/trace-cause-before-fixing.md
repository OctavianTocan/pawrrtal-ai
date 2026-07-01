---
name: trace-cause-before-fixing
paths: ["**/*.{ts,tsx,css}"]
---

# Trace the Full Code Path From Trigger to Render Before Writing a Fix

Before writing any fix for a visual or behavioral bug, trace the full
code path from trigger to render. Don't fix downstream symptoms.

Answer two questions in sequence:

1. "What is the immediate cause of the visible problem?"
2. "Is my change targeting that cause, or a downstream symptom?"

If targeting a symptom, stop and trace further upstream.

## Verify

"Am I about to change CSS/JSX without first checking whether the
trigger condition (class application, state change, hook return value)
fires at all? Did I trace from the trigger to the render output?"

## Patterns

Bad — fixes animation values without checking if the class is applied:

```css
/* Updated keyframes but the hook never returns true */
@keyframes navbar-item-in { ... }
```

Good — checks the hook first, finds it never fires on cached sessions:

```ts
// useNavbarFadeIn only triggered on loading→resolved transition
// Cached sessions skip loading, so it never fires
return isHomeRoute && !authLoading; // simplified
```

Bad — adds positioning hack without checking parent layout:

```tsx
{/* Parent already has flex items-center */}
<div className="relative left-1/2 -translate-x-1/2 flex">
```

Good — reads parent first, uses flex centering:

```tsx
{/* Parent centers children — just add justify-center to the row */}
<div className="flex items-center justify-center">
```
