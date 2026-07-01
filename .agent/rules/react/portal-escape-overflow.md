---
name: portal-escape-overflow
paths: ["**/*.{ts,tsx}"]
---
# Portals to Escape Overflow and Stacking Contexts

When a dropdown or tooltip renders inside a parent with `overflow: hidden`,
CSS transforms (Framer Motion), or z-index stacking contexts, it will be
clipped. Use `createPortal` to render to `document.body` with Floating UI
`strategy: 'fixed'`. Extend click-outside detection to include both the
trigger ref and the portaled element ref.

## Verify

"Is this dropdown/tooltip inside a parent with overflow-hidden or CSS
transforms? Should I portal it out?"

## Patterns

Bad — dropdown trapped inside overflow-hidden + transform:

```tsx
<motion.div className="overflow-hidden">
  <button onClick={() => setOpen(true)}>Menu</button>
  {open && <DropdownMenu items={items} />}
</motion.div>
```

Good — portaled to body, click-outside checks both refs:

```tsx
<motion.div className="overflow-hidden">
  <button ref={triggerRef} onClick={() => setOpen(true)}>Menu</button>
</motion.div>
{open && createPortal(
  <DropdownMenu
    ref={menuRef}
    style={{ position: 'fixed', ...floatingStyles }}
    items={items}
  />,
  document.body
)}
```
