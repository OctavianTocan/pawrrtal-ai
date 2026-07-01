---
name: inline-styles-error-overlays
paths: ["**/*.{ts,tsx}"]
---
# Error Overlays Must Use Inline Styles

Error overlays that depend on CSS or Tailwind will be invisible if CSS
loading itself fails. Use inline `style` attributes with hardcoded colors
and positioning. Never Tailwind classes for error UI.

## Verify

"If CSS completely fails to load, will this error boundary still be visible?"

## Patterns

Bad — error overlay invisible when CSS fails:

```tsx
<div className="fixed inset-0 bg-red-600 text-white z-50">
  Something went wrong
</div>
```

Good — visible regardless of CSS loading:

```tsx
<div style={{
  position: 'fixed',
  inset: 0,
  background: '#dc2626',
  color: 'white',
  zIndex: 99999,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}}>
  Something went wrong
</div>
```
